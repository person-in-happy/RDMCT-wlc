import unittest
from types import SimpleNamespace
from terminal_cleanup_bound import cleanup_certificate


class CleanupTests(unittest.TestCase):
    def cfg(self):
        return SimpleNamespace(source='dual',chambers=(1,2),handling=1,rotation=2,vtr_travel=2,
            upper_reset=30,lower_reset=25,cleaning_time=500,module_residency=10000,
            robot_residency=10000,horizon=100000)

    def test_retains_post_product_cleaning_allowance(self):
        c=cleanup_certificate(self.cfg(),950,dict(pairs=16,cycles_per_chamber=4))
        self.assertEqual(c['normal_form_horizon'],2436)
        self.assertGreater(c['normal_form_horizon'],950+2*500)

    def test_both_mixed_configurations(self):
        for upper,p,q,want in ((905,28,9,2759),(1398,24,8,3140)):
            self.assertEqual(cleanup_certificate(self.cfg(),upper,dict(pairs=p,cycles_per_chamber=q))['normal_form_horizon'],want)

    def test_reject_short_residency_and_single_source(self):
        cfg=self.cfg();cfg.robot_residency=100
        with self.assertRaises(ValueError):cleanup_certificate(cfg,950,dict(pairs=16,cycles_per_chamber=4))
        cfg=self.cfg();cfg.source='single'
        with self.assertRaises(ValueError):cleanup_certificate(cfg,950,dict(pairs=16,cycles_per_chamber=4))


if __name__=='__main__':unittest.main()
