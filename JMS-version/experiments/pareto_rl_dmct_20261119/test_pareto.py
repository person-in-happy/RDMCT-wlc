"""Regression tests for the metric definitions and unsimplified event witness."""
import math
import unittest
from copy import deepcopy

from common import config, lower_bound, metrics
from decoder import Decoder, Retiming
from evaluate import hits, hv, igdplus, reference
from evolution import ranks
from native import Native
from validate import validate


class ObjectiveTests(unittest.TestCase):
    def test_independent_reference(self):
        truth, unsupported = reference()
        bounds = ((331, 519), (42, 424 / 3))
        self.assertEqual((len(truth), len(unsupported)), (7, 3))
        self.assertEqual(unsupported, [(514, 90), (516, 85), (517, 77)])
        self.assertAlmostEqual(hv(truth, bounds), .378339, places=6)
        supported = [p for p in truth if p not in unsupported]
        self.assertAlmostEqual(hv(supported, bounds) / hv(truth, bounds), .9706, places=4)
        self.assertEqual(igdplus(truth, truth, bounds), 0)
        self.assertGreater(igdplus(supported, truth, bounds), 0)
        self.assertEqual(hits(supported, truth), 4)

    def test_hv_discards_dominated_and_outside_points(self):
        bounds = ((0, 1), (0, 1))
        points = [(0.2, 0.8), (0.7, 0.2)]
        self.assertAlmostEqual(hv(points, bounds), .9 * .3 + .4 * .6)
        self.assertAlmostEqual(hv(points + [(0.7, 0.8), (1.2, 0), (0, 2)], bounds), hv(points, bounds))

    def test_pair_screen(self):
        cfg = config("M4")
        self.assertEqual(lower_bound(cfg, 4, 0), 54)
        self.assertAlmostEqual(lower_bound(cfg, 4, 1), 40 + 280 / 3)
        self.assertGreater(lower_bound(cfg, 4, 2), lower_bound(cfg, 4, 1))
        with self.assertRaises(ValueError):
            lower_bound(cfg, 4, 3)

    def test_nondominated_ranks_and_crowding(self):
        vals = [(1, 5), (2, 3), (4, 1), (3, 4)]
        fitness = ranks(list(enumerate(vals)))
        self.assertEqual([r for r, _ in fitness], [0, 0, 0, 1])
        self.assertEqual(fitness[0][1], -math.inf)
        self.assertEqual(fitness[2][1], -math.inf)
        self.assertAlmostEqual(fitness[1][1], -2)


class PhysicalWitnessTests(unittest.TestCase):
    def test_late_clean_is_detected_even_if_the_physical_route_replays(self):
        cfg = config("S1")
        dec = Decoder(cfg)
        genes = (0, 0, 2, 1, 0, 0, 0, 0, 0, 0)
        original = Retiming(dec.build(genes, dec.pairing(genes)), 25).solve("B", None, 5)
        later = deepcopy(original)
        clean = next(c for c in later["cycles"] if c["mode"]=="clean")
        pair_ids = set(clean["pairs"])
        delta = .9*cfg.horizon-clean["start"]
        clean["start"] += delta
        clean["end"] += delta
        names = set()
        for j in later["jobs"]:
            if j["pair"] in pair_ids:
                names.add(j["name"])
                for k in ("loan_start","loan_end","load_start","load_end","unload_start","unload_end"):
                    j[k] += delta
        for e in later["events"]:
            belongs = (e.get("pair") in pair_ids or e.get("job") in names or
                       (e.get("chamber")==clean["chamber"] and e.get("cycle")==clean["index"]))
            if belongs:
                e["start"] += delta
                e["end"] += delta
        self.assertTrue(validate(later)["valid"])
        self.assertAlmostEqual(metrics(original,25)["secondary"],metrics(later,25)["secondary"])
        full = Native(cfg,1,25)
        try:
            self.assertTrue(full.warm(original))
            self.assertFalse(full.warm(later))
        finally:
            full.close()

    def test_fractional_retiming_and_original_rows(self):
        cfg = config("S1")
        dec = Decoder(cfg)
        # Interleaved alignment operations make the optimal maximum wait fractional.
        genes = (0, 0, 2, 1, 0, 0, 0, 0, 0, 0)
        timing = Retiming(dec.build(genes, dec.pairing(genes)), 25)
        schedule = timing.solve("B", None, 5)
        self.assertIsNotNone(schedule)
        self.assertTrue(validate(schedule)["valid"])
        self.assertTrue(any(abs(e["start"] - round(e["start"])) > 1.e-4 for e in schedule["events"]))
        solver = Native(cfg, 1, 25)
        try:
            self.assertTrue(solver.warm(schedule))
            inconsistent = deepcopy(schedule)
            inconsistent["cmax"] = 0
            self.assertFalse(solver.warm(inconsistent))
        finally:
            solver.close()
        self.assertAlmostEqual(metrics(schedule, 0)["secondary"], metrics(schedule, 50)["secondary"])


if __name__ == "__main__":
    unittest.main()
