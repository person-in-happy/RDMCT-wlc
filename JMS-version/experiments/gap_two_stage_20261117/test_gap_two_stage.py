"""Regression checks for scientific gating, restricted refinement and safe retries."""
import importlib.util
import io
from pathlib import Path
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys

HERE = Path(__file__).resolve().parent
loader = importlib.util.spec_from_file_location("gap_runner", HERE / "gap_two_stage.py")
g = importlib.util.module_from_spec(loader)
loader.loader.exec_module(g)


def primary(ub=104., lb=100., gap=.04, seconds=200., status="gaplimit"):
    return dict(primal_bound=ub, dual_bound=lb, relative_gap=gap, seconds=seconds, status=status)


class ProtocolTests(unittest.TestCase):
    def test_gap_gate_and_remaining_budget(self):
        row = g.gate(primary(), .05, 300.)
        self.assertTrue(row["switch"])
        self.assertEqual(row["remaining_seconds"], 100.)
        self.assertFalse(g.gate(primary(ub=110., gap=.1), .05, 300.)["switch"])
        self.assertFalse(g.gate(primary(seconds=301., status="timelimit"), .05, 300.)["switch"])
        self.assertFalse(g.gate(primary(status="memlimit"), .05, 300.)["switch"])

    def test_no_certificate_from_zero_infinite_or_inconsistent_bounds(self):
        for lb in (0., -1., None, g.finite(-1e20)):
            with self.subTest(lb=lb):
                self.assertFalse(g.gate(primary(lb=lb, gap=.01), .05, 300.)["quality_met"])
        self.assertFalse(g.gate(primary(lb=105.), .05, 300.)["quality_met"])
        self.assertFalse(g.gate(primary(ub=120., gap=.001), .05, 300.)["quality_met"])
        self.assertIsNone(g.finite(float("inf")))
        self.assertIsNone(g.finite(float("nan")))

    def test_zero_threshold_requires_optimal_status(self):
        self.assertFalse(g.gate(primary(ub=100., gap=0.), 0., 300.)["switch"])
        self.assertTrue(g.gate(primary(ub=100., gap=0., status="optimal"), 0., 300.)["switch"])

    def test_all_nine_cells_and_no_small_reference_case(self):
        cells = g.make_cells([dict(case=n, backend=n[0]) for n in g.CASES])
        self.assertEqual(len({c["id"] for c in cells}), 9)
        self.assertEqual({c["seed"] for c in cells}, {1, 2, 3})
        self.assertFalse(any("n2_" in c["id"] for c in cells))

    def test_completed_outcomes_are_never_retried_for_better_results(self):
        for ev in (dict(gate=dict(quality_met=False)), dict(budget_eligible=False)):
            self.assertFalse(g.retryable(dict(state="completed", evidence=ev), explicit=True))
        self.assertTrue(g.retryable(dict(state="incomplete")))
        self.assertTrue(g.retryable(dict(state="failed", failure=dict(reason="RAM_guard"))))
        self.assertFalse(g.retryable(dict(state="failed", failure=dict(reason="worker_exception"))))
        self.assertTrue(g.retryable(dict(state="failed", failure=dict(reason="worker_exception")), True))

    def test_large_jobs_are_serialized_and_future_memory_is_reserved(self):
        settings = dict(min_available_gib=8., large_reservation_gib=12., small_reservation_gib=4.)
        small, large = dict(case="D_n4_mixed"), dict(case="D_n16_4x1")
        self.assertFalse(g.can_launch(large, [], 19., settings, 2))
        self.assertTrue(g.can_launch(large, [], 20., settings, 2))
        self.assertFalse(g.can_launch(large, [dict(cell=large, rss_gib=2.)], 28., settings, 2))
        self.assertFalse(g.can_launch(small, [dict(cell=large, rss_gib=1.)], 22., settings, 2))
        self.assertTrue(g.can_launch(small, [dict(cell=large, rss_gib=12.)], 12., settings, 2))

    def test_scoped_process_detection_and_exclusive_controller(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            args = [sys.executable, str(g.HERE / "gap_two_stage.py"), "worker", "--campaign", str(out)]
            self.assertEqual(g.process_role(args, out), "worker")
            self.assertIsNone(g.process_role(args, out / "another_campaign"))
            with g.controller_lock(out):
                with self.assertRaises(RuntimeError):
                    with g.controller_lock(out):
                        pass
            with g.controller_lock(out):
                pass


class SCIPIntegrationTests(unittest.TestCase):
    def test_real_scip_refinement_resets_gap_and_only_fixes_structure(self):
        from pyscipopt import Model
        m = Model()
        m.hideOutput()
        z = m.addVar("structure", vtype="B")
        sync = m.addVar("sync_choice", vtype="B")
        a = m.addVar("Cmax", lb=10.)
        b = m.addVar("B", lb=0.)
        m.addCons(a >= 10 + 2 * z)
        m.addCons(b >= 5 - 4 * sync)
        m.setObjective(a)
        m.setRealParam("limits/gap", .05)
        m.optimize()
        x = SimpleNamespace(model=m, cmax=a, secondary_objective=b)
        # A known feasible primary assignment with room for secondary gain.
        vals = {"structure": 0., "sync_choice": 0., "Cmax": 10., "B": 5.}
        g.start_refinement(x, vals, 10., 17.)
        self.assertEqual(m.getSolvingTime(), 0.)
        self.assertEqual(m.getParam("limits/gap"), 0.)
        self.assertEqual(m.getParam("limits/time"), 17.)
        self.assertEqual(z.getLbOriginal(), 0.)
        self.assertEqual(z.getUbOriginal(), 0.)
        self.assertEqual(sync.getUbOriginal(), 1.)
        sol = m.createSol()
        for v in m.getVars(transformed=False):
            m.setSolVal(sol, v, vals[v.name])
        self.assertTrue(m.checkSol(sol, completely=True, original=True))
        m.addSol(sol)
        m.optimize()
        self.assertEqual(str(m.getStatus()), "optimal")
        self.assertAlmostEqual(m.getVal(b), 1.)
        self.assertLessEqual(m.getVal(a), 10. + 2e-6)
        m.freeProb()

    def test_worker_end_to_end_and_no_gate_path(self):
        from pyscipopt import Model
        class Toy:
            def __init__(self, cfg):
                self.cfg, self.Q = cfg, 0
                self.model = m = Model()
                m.hideOutput()
                self.cmax = m.addVar("Cmax", lb=10.)
                self.max_wait = m.addVar("max_wait", lb=0.)
                self.z = m.addVar("structure", vtype="B")
                self.sync = m.addVar("sync_choice", vtype="B")
                m.addCons(self.cmax >= 10 + 2 * self.z)
                m.addCons(self.max_wait >= 5 - 4 * self.sync)
                self.primary_objective, self.secondary_objective = self.cmax, self.max_wait
            def result(self, solution):
                m = self.model
                return dict(metrics=dict(cmax=m.getSolVal(solution, self.cmax),
                                         wait_max=m.getSolVal(solution, self.max_wait),
                                         secondary=m.getSolVal(solution, self.max_wait)))
        for block_gate in (False, True):
            with self.subTest(block_gate=block_gate), TemporaryDirectory() as tmp:
                out = Path(tmp)
                cid = "D_n4_mixed__s1__gap_two_stage"
                dest = out / "runs" / cid / "attempts/0001"
                values = out / "source_values.json"
                g.f.dump(values, dict(values=dict(Cmax=10., max_wait=5., structure=0., sync_choice=0.)))
                spec = dict(cells=[dict(id=cid, case="D_n4_mixed", backend="D", seed=1, budget=300.)],
                            cases=[dict(case="D_n4_mixed", config=dict(chambers=[]), values=str(values), scales={})],
                            relative_gap=.05, settings=dict(solver_budget_tolerance=1.))
                g.f.dump(out / "campaign.json", spec)
                g.f.dump(dest / "launch.json", {})
                fake = dict(model=SimpleNamespace(Config=lambda **kw: SimpleNamespace(**kw), Integrated=Toy),
                            validate=SimpleNamespace(validate=lambda _: dict(valid=True)))
                real_gate = g.gate
                def decide(row, threshold, total):
                    if block_gate:
                        row = row | dict(status="timelimit", seconds=300., primal_bound=10., dual_bound=0., relative_gap=None)
                    return real_gate(row, threshold, total)
                with patch.object(g, "checked", return_value=spec), patch.dict(sys.modules, fake), \
                     patch.object(g.f, "physical_metrics", side_effect=lambda d: d["metrics"]), \
                     patch.object(g, "gate", side_effect=decide), redirect_stdout(io.StringIO()):
                    g.worker(out, cid, "0001")
                ev = g.f.read(dest / "evidence.json")
                self.assertTrue(ev["valid"])
                self.assertTrue(ev["budget_eligible"])
                self.assertEqual(ev["gate"]["switch"], not block_gate)
                self.assertEqual(len(ev["stages"]), 1 if block_gate else 2)
                self.assertEqual(g.inspect_cell(out, cid)["state"], "completed")
                self.assertFalse(g.retryable(g.inspect_cell(out, cid), True))
                g.f.dump(dest / "failure.json", dict(reason="worker_exception", message="cleanup after completed certificate"))
                self.assertEqual(g.inspect_cell(out, cid)["state"], "completed")
                self.assertFalse(g.retryable(g.inspect_cell(out, cid), True))


if __name__ == "__main__":
    unittest.main()
