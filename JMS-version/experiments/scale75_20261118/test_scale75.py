import tempfile
import unittest
from pathlib import Path

import run
from packing import Packing
from timing import BatchTiming


class Scale75Tests(unittest.TestCase):
    def test_mixed_odd_inventory_across_checkpoints(self):
        cfg = run.Config(run.ports(11, "mixed"))
        search = Packing(cfg)
        beam = search.advance([()], 8)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"search.json"
            run.checkpoint(path, "protocol", dict(depth=1, beam=beam))
            saved = run.restore(path, "protocol")["beam"]
            recovered = [tuple(tuple(x) for x in plan) for plan in saved]
            self.assertEqual(search.advance(beam, 8), search.advance(recovered, 8))
            with self.assertRaises(ValueError):
                run.restore(path, "other protocol")
        for _ in range(1, search.n):
            beam = search.advance(beam, 8)
        timing = BatchTiming(search, beam[0])
        a = timing.solve("A", timing.initial)
        before = timing.schedule(a["starts"])
        b = timing.solve("B", a["starts"], before["cmax"])
        after = timing.schedule(b["starts"])
        self.assertTrue(a["initial_accepted"] and b["initial_accepted"])
        self.assertEqual(sum(j["product"] for j in after["jobs"]), 11)
        self.assertEqual(after["cmax"], before["cmax"])
        self.assertLessEqual(run.physical_metrics(after)["secondary"], run.physical_metrics(before)["secondary"]+2e-4)
        self.assertTrue(after["validation"]["valid"])
        self.assertGreater(after["validation"]["cleaning_count"], 0)
        self.assertGreater(run.physical_metrics(after)["rhythm_centers"], 0)
        self.assertFalse(after["global_optimality_claim"])


if __name__ == "__main__":
    unittest.main()
