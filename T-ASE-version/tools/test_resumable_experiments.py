"""Recovery tests use temporary models and injected solvers; no benchmark is launched."""
from pathlib import Path
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import resumable_experiments as r
import benchmark_resume_guard as g


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root / "campaign"
        self.out.mkdir()
        self.source = self.root / "model.lp"
        self.source.write_text("frozen model")
        self.source.with_suffix(".cie.json").write_text('{"config": {}}')
        self.manifest = dict(
            files=[str(self.source)], assets={str(self.source): r.sha(self.source)},
            options=dict(seeds="1,2,3", construction_limit=30))
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def construct(self, directory, name, cfg, **kwargs):
        seed = kwargs["random_seed"]
        self.calls.append(seed)
        solution = Path(directory) / "warmstart.sol"
        solution.write_text(str(seed))
        return str(solution)

    def run_spbs(self, construct=None, validate=None):
        with contextlib.redirect_stdout(io.StringIO()):
            r.run_spbs(self.out, self.manifest, construct or self.construct,
                       validate or (lambda *args: (True, "valid")), lambda **kw: kw)

    def test_interrupt_then_resume_skips_completed_and_preserves_attempt(self):
        def interrupted(*args, **kwargs):
            if kwargs["random_seed"] == 2:
                Path(args[0], "interrupted.txt").write_text("partial")
                raise KeyboardInterrupt()
            return self.construct(*args, **kwargs)
        with self.assertRaises(KeyboardInterrupt):
            self.run_spbs(interrupted)
        self.assertEqual(len(r.read_json(self.out / "records.json")), 1)
        self.run_spbs()
        self.assertEqual(self.calls, [1, 2, 3])
        self.assertEqual(len(list(self.out.rglob("interrupted.txt"))), 1)
        self.assertEqual(len(list((self.out / "cases/model/seed_2").iterdir())), 2)
        self.run_spbs()
        self.assertEqual(self.calls, [1, 2, 3])
        self.assertEqual(len(r.read_json(self.out / "records.json")), 3)

    def test_no_incumbent_is_completed_not_infeasible(self):
        calls = []
        def none(*args, **kwargs):
            calls.append(kwargs["random_seed"])
        self.run_spbs(none)
        self.run_spbs(none)
        self.assertEqual(calls, [1, 2, 3])
        self.assertTrue(all(not row["has_solution"] for row in r.read_json(self.out / "records.json")))

    def test_invalid_solution_stays_blocked(self):
        with self.assertRaisesRegex(RuntimeError, "validation"):
            self.run_spbs(validate=lambda *args: (False, "incompatible"))
        with self.assertRaisesRegex(RuntimeError, "compatibility"):
            self.run_spbs()
        self.assertEqual(self.calls, [1])
        self.assertFalse((self.out / "complete.json").exists())

    def test_changed_solution_cannot_be_skipped(self):
        self.run_spbs()
        row = r.read_json(self.out / "records.json")[0]
        Path(row["solution"]).write_text("tampered")
        with self.assertRaisesRegex(RuntimeError, "missing/changed"):
            self.run_spbs()

    def test_atomic_write_keeps_previous_commit(self):
        path = self.out / "records.json"
        r.atomic_json(path, [1])
        with patch.object(r.os, "replace", side_effect=OSError("power loss")):
            with self.assertRaises(OSError):
                r.atomic_json(path, [1, 2])
        self.assertEqual(r.read_json(path), [1])

    def test_missing_csv_is_rebuilt_without_solving(self):
        self.run_spbs()
        (self.out / "records.csv").unlink()
        self.run_spbs()
        self.assertEqual(self.calls, [1, 2, 3])
        self.assertEqual(len((self.out / "records.csv").read_text().splitlines()), 4)

    def test_lock_blocks_second_writer_and_releases(self):
        with r.campaign_lock(self.out):
            with self.assertRaisesRegex(RuntimeError, "lock"):
                with r.campaign_lock(self.out):
                    pass
        with r.campaign_lock(self.out):
            pass

    def test_tail_repair_preserves_backup_and_future_appends(self):
        path = self.out / "checkpoint.jsonl"
        original = b'{"record_type":"meta"}\n{"partial":'
        path.write_bytes(original)
        r.repair_checkpoint_tail(path)
        self.assertEqual(path.read_bytes(), b'{"record_type":"meta"}\n')
        self.assertEqual(next(self.out.glob("*.bak")).read_bytes(), original)
        with path.open("ab") as stream:
            stream.write(b'{"record_type":"row"}\n')
        r.repair_checkpoint_tail(path)
        self.assertEqual(len(path.read_text().splitlines()), 2)

    def test_interior_corruption_is_not_discarded(self):
        path = self.out / "checkpoint.jsonl"
        path.write_text('broken\n{"ok":1}\n')
        with self.assertRaisesRegex(RuntimeError, "interior"):
            r.repair_checkpoint_tail(path)

    def test_changed_assets_block_resume(self):
        self.source.write_text("changed model")
        with self.assertRaisesRegex(RuntimeError, "hash changed"):
            r.verify_assets(self.manifest)

    def test_guard_rejects_other_signature_before_loader(self):
        folder = self.out / "runs/baselines/.checkpoints"
        folder.mkdir(parents=True)
        (folder / "old.jsonl").write_text("{}\n")
        with self.assertRaisesRegex(RuntimeError, "signature changed"):
            g.guarded_load(lambda *args: self.fail("loader must not run"),
                           folder / "new.jsonl", "new", self.out)

    def test_guard_archives_partial_reports_outside_analyzer_tree(self):
        folder = self.out / "runs/baselines/.checkpoints"
        folder.mkdir(parents=True)
        partial = folder.parent / "partial_raw.csv"
        partial.write_text("raw evidence")
        rows, complete = g.guarded_load(lambda *args: ({"one": 1}, None),
                                       folder / "same.jsonl", "same", self.out)
        self.assertEqual(rows, {"one": 1})
        self.assertFalse(partial.exists())
        self.assertEqual(next((self.out / "attempt_history").rglob("*.csv")).read_text(), "raw evidence")

    def test_sensitivity_failed_batch_then_same_paths_and_analysis(self):
        output = self.out / "runs/baselines"
        command = [sys.executable, str(r.ROOT / "cie/code/run_cie_benchmarks.py"),
                   "--output_dir", str(output), "--solution_dir", str(self.out / "solutions/baselines")]
        manifest = {"commands": [command]}
        with self.assertRaises(subprocess.CalledProcessError):
            with contextlib.redirect_stdout(io.StringIO()):
                r.run_sensitivity(self.out, manifest,
                                  lambda *args: (_ for _ in ()).throw(subprocess.CalledProcessError(1, command)))
        calls = []
        def finish(cmd, log):
            calls.append(cmd)
            if "--output_dir" in cmd and "benchmark_resume_guard.py" in cmd[1]:
                self.assertEqual(cmd[2:], command[2:])
                folder = output / ".checkpoints"
                folder.mkdir(parents=True)
                artifact = output / "final.json"
                artifact.write_text("{}")
                (folder / "resume.jsonl").write_text(
                    json.dumps({"record_type": "complete", "artifacts": [str(artifact)]}) + "\n")
        with contextlib.redirect_stdout(io.StringIO()):
            r.run_sensitivity(self.out, manifest, finish)
        self.assertEqual(len(calls), 3)
        self.assertTrue((self.out / "complete.json").exists())

    def test_zero_exit_without_complete_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, "unfinished"):
            with contextlib.redirect_stdout(io.StringIO()):
                r.run_sensitivity(self.out, {"commands": [
                    ["python", "runner", "--output_dir", str(self.out / "runs/baselines")]]},
                    lambda *args: None)


if __name__ == "__main__":
    unittest.main(verbosity=2)

