"""No optimization: validate scan coverage, scalar ordering and resume scoping."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

path = Path(__file__).with_name("sensitivity.py")
loader = importlib.util.spec_from_file_location("weight_sensitivity_tested", path)
s = importlib.util.module_from_spec(loader)
loader.loader.exec_module(s)


class SensitivityTests(unittest.TestCase):
    def test_matched_scan_has_no_repeated_old_weight_or_n2(self):
        cases = [dict(case=c, backend="E" if c.startswith("E_") else "D") for c in s.CASES]
        cells = s.make_cells(cases, s.WEIGHTS)
        self.assertEqual(len(cells), 45)
        self.assertEqual(len({c["id"] for c in cells}), 45)
        self.assertEqual(sum(c["budget"] for c in cells), 13500)
        self.assertEqual({c["seed"] for c in cells}, {1, 2, 3})
        self.assertTrue(all(c["method"] == "scip" and c["budget"] == 300 for c in cells))
        with self.assertRaises(ValueError):
            s.checked_weights([0.01])

    def test_existing_objective_changes_preference_across_known_crossing(self):
        class Model:
            def setObjective(self, value, sense):
                self.value = value
        def score(a, b, rho):
            x = SimpleNamespace(model=Model(), cmax=a, secondary_objective=b)
            s.f.configure_objective(x, "joint_" + str(rho), {"cmax": 542, "secondary": 499})
            return x.model.value
        self.assertLess(score(541, 1694, 0.0005), score(542, 499, 0.0005))
        self.assertGreater(score(541, 1694, 0.001), score(542, 499, 0.001))
        for rho in s.WEIGHTS:
            self.assertLess(score(920, 1044, rho), score(920, 1523, rho))

    def test_process_matching_is_exact_and_campaign_scoped(self):
        self.assertEqual(s.process_role(["python", str(path), "resume", "--campaign", str(s.DEFAULT)], s.DEFAULT), "resume")
        self.assertEqual(s.process_role(["python", str(s.BASE_ENTRY), "worker", "--campaign", str(s.DEFAULT)], s.DEFAULT), "worker")
        self.assertIsNone(s.process_role(["python", str(s.BASE_ENTRY), "worker", "--campaign", str(s.BASE)], s.DEFAULT))
        self.assertIsNone(s.process_role(["python", str(path), "plan", "--campaign", str(s.DEFAULT)], s.DEFAULT))

    def test_plan_is_read_only_and_never_calls_model_or_runner(self):
        with patch.object(s.f, "prepare", side_effect=AssertionError("prepare during plan")), \
             patch.object(s.f, "worker", side_effect=AssertionError("worker during plan")), \
             patch.object(s.f, "run", side_effect=AssertionError("run during plan")), \
             patch.object(s.f, "dump", side_effect=AssertionError("write during plan")):
            plan = s.make_plan(s.WEIGHTS)
        self.assertFalse(plan["solver_started"])
        self.assertEqual(plan["cells"], 45)
        self.assertEqual(plan["nominal_solver_hours"], 3.75)


if __name__ == "__main__":
    unittest.main()
