import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/"scale75_20261118"))
import run as original
from search import Search, flexible_blocks, fixed_timing, workload_bound
from neighborhood import WindowSearch


class RepackTests(unittest.TestCase):
    def test_precedence_windows_and_chamber_bound(self):
        cfg = original.Config(original.ports(11, "mixed"))
        search = Search(cfg)
        beam = [()]
        for _ in range(search.n):
            beam = search.next_layer(beam, 3)
        plan = beam[0]
        blocks = flexible_blocks(search, plan)
        starts = [at+t for (k,ch,at), p in zip(plan, blocks) for t in p.times]
        local = WindowSearch(cfg, blocks)
        old = local.finish(starts)
        for lo, hi in [(0,350), (250,850), (old-350,old+250)]:
            starts, row = local.solve(starts, lo, hi, 75, 2.)
            self.assertLessEqual(row["upper_after"], row["upper_before"])
            self.assertTrue(fixed_timing(cfg,blocks,starts).schedule(starts)["validation"]["valid"])
        self.assertLessEqual(workload_bound(cfg)["seconds"], local.finish(starts))


if __name__ == "__main__":
    unittest.main()
