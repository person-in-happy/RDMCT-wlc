"""No formal solves: verify factorial scope, isolation and unbiased paired summaries."""
from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import subprocess
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
loader = importlib.util.spec_from_file_location("gap_perturbation", HERE / "sensitivity.py")
s = importlib.util.module_from_spec(loader)
loader.loader.exec_module(s)


def observation(variant, seed, b, switched=False, eligible=True, budget=300., factor="gap"):
    return dict(variant=variant, seed=seed, case="D_n4_mixed", eligible=eligible, state="completed",
                factor=factor, gap_target=.05 if factor == "reference" else .1, budget=budget,
                quality_met=switched, switched=switched, actual_primary_gap=.04 if switched else 3.67,
                primary_seconds=100. if switched else budget, secondary_seconds=20. if switched else 0.,
                switch_seconds=100. if switched else None, refinement_B_gain=10. if switched else 0.,
                wall_seconds=budget+2., cmax=542., secondary=b, wait_sum=10., wait_max=3., rhythm=0., rhythm_centers=0)


class DesignTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "PowerShell controller integration")
    def test_foreground_controller_handles_zero_and_two_variants_without_solving(self):
        for count in (0, 2):
            with self.subTest(variants=count), TemporaryDirectory() as tmp:
                root = Path(tmp)
                members = [dict(id=f"variant{i}", gap=.01 + i*.09, budget=300.,
                                campaign=str(root / f"case{i}"), engine="fake_engine.py") for i in range(count)]
                (root / "members.json").write_text(json.dumps(members), encoding="utf-8")
                stub = root / "fake_python.ps1"
                stub.write_text("""if ($args -contains 'members') {
    Get-Content -LiteralPath (Join-Path $PSScriptRoot 'members.json') -Raw
} elseif ($args -contains 'resume') {
    $line=ConvertTo-Json -InputObject @($args) -Compress
    Add-Content -LiteralPath (Join-Path $PSScriptRoot 'launches.jsonl') -Value $line
} else { '{}' }
$global:LASTEXITCODE=0
""", encoding="utf-8")
                result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                         "-File", str(HERE / "control.ps1"), "-Action", "Run", "-Suite", str(root),
                                         "-Python", str(stub)], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                log = root / "launches.jsonl"
                launches = [json.loads(line) for line in log.read_text(encoding="utf-8-sig").splitlines()] if log.exists() else []
                self.assertEqual(len(launches), count)
                for i, args in enumerate(launches):
                    self.assertEqual(args[args.index("--campaign") + 1], members[i]["campaign"])
                    self.assertEqual(args[args.index("--max-workers") + 1], "2")
                    self.assertIn("fake_engine.py", args)

    def test_minimal_reuses_five_percent_and_adds_only_eighteen(self):
        rows = s.matrix([.01, .05, .1], [300])
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(r["flows"] for r in rows if not r["reuse"]), 18)
        self.assertEqual(sum(r["reuse"] for r in rows), 1)
        self.assertEqual({r["gap"] for r in rows}, {.01, .05, .1})

    def test_budget_axis_is_separate_not_cartesian(self):
        rows = s.matrix([.01, .05, .1], [300, 600, 1200])
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(r["flows"] for r in rows if not r["reuse"]), 36)
        self.assertTrue(all(r["gap"] == .05 for r in rows if r["budget"] != 300))
        only_budget = s.matrix([.05], [600, 1200])
        self.assertEqual(sum(r["budget"] * r["flows"] / 60 for r in only_budget if not r["reuse"]), 270.)

    def test_extended_grid_and_invalid_parameters(self):
        self.assertEqual(len(s.matrix([0, .01, .05, .1, .2], [300])), 5)
        for gap in (-.1, 1., float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                s.matrix([gap], [300])
        for budget in (0., -10., 3600., float("inf")):
            with self.assertRaises(ValueError):
                s.matrix([.05], [budget])

    def test_unswitched_samples_stay_in_means_and_missing_pairs_are_visible(self):
        rows = [observation("base", seed, 500., factor="reference") for seed in (1, 2, 3)]
        rows += [observation("gap10", 1, 490., True), observation("gap10", 2, 500.),
                 observation("gap10", 3, 1., True, eligible=False)]
        groups, pairs = s.summarize(rows)
        group = next(r for r in groups if r["variant"] == "gap10")
        self.assertEqual(group["eligible"], 2)
        self.assertFalse(group["complete"])
        self.assertEqual(group["switch_rate_of_eligible"], .5)
        self.assertEqual(group["mean_secondary"], 495.)
        self.assertEqual(group["mean_secondary_seconds"], 10.)
        self.assertEqual(group["conditional_mean_switch_seconds"], 100.)
        self.assertEqual(sum(r["paired"] for r in pairs), 2)
        self.assertNotIn("delta_secondary", next(r for r in pairs if r["seed"] == 3))

    def test_budget_difference_is_not_labeled_equal_budget(self):
        groups, pairs = s.summarize([observation("base", 1, 500., factor="reference"),
                                    observation("b600", 1, 480., budget=600., factor="budget")])
        self.assertFalse(pairs[0]["equal_budget"])
        self.assertEqual(pairs[0]["delta_secondary"], -20.)
        self.assertEqual(pairs[0]["delta_B_percent"], -4.)
        self.assertIsNone(groups[0]["conditional_mean_switch_seconds"])

    def test_reachability_does_not_extrapolate_an_early_reference_switch(self):
        ev = dict(valid=True, budget_eligible=True, stages=[dict(relative_gap=.04, status="gaplimit",
                  primal_bound=104., dual_bound=100., seconds=10.)], gate=dict(switch=True))
        with patch.object(s, "reference", return_value=dict(cells=[dict(id="c", case="case", seed=1)])), \
             patch.object(s.g, "inspect_cell", return_value=dict(state="completed", evidence=ev)):
            rows = s.diagnose(Path("unused"), [.01, .1])["rows"]
        self.assertEqual(rows[0]["diagnosis"], "unknown_after_reference_early_switch")
        self.assertEqual(rows[1]["diagnosis"], "observed_endpoint_meets_target_not_a_rerun")

    def test_prepare_freezes_new_campaigns_without_writing_reference(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            ref, out = root / "reference", root / "new_suite"
            cases = [dict(case=name, backend=name[0]) for name in s.g.CASES]
            original = dict(relative_gap=.05, cells=s.g.make_cells(cases), cases=cases,
                            assets={}, sources={}, references=[dict(marker="old-weighted-300s")],
                            settings=dict(min_available_gib=8.),
                            environment=dict(python_version=sys.version, packages={}))
            s.f.dump(ref / "campaign.json", original)
            s.f.dump(ref / "contract.json", dict(campaign_sha256=s.f.sha(ref / "campaign.json")))
            before = {p.relative_to(ref): p.read_bytes() for p in ref.rglob("*") if p.is_file()}
            with redirect_stdout(io.StringIO()):
                s.prepare(out, [.05, .1], [300, 600], ref)
            suite = s.checked(out)
            self.assertEqual(suite["new_flows"], 18)
            self.assertEqual({p.relative_to(ref): p.read_bytes() for p in ref.rglob("*") if p.is_file()}, before)
            for m in suite["members"]:
                cfg = s.f.read(Path(m["campaign"]) / "campaign.json")
                self.assertEqual(cfg["cases"], original["cases"])
                self.assertEqual(cfg["settings"], original["settings"])
                if m["budget"] != 300:
                    self.assertEqual(cfg["references"], [])
                    self.assertFalse(cfg["weighted_comparison_enabled"])
                if not m["reuse"]:
                    self.assertEqual({c["budget"] for c in cfg["cells"]}, {m["budget"]})
            with self.assertRaises(FileExistsError):
                s.prepare(out, [.05], [300], ref)


if __name__ == "__main__":
    unittest.main()
