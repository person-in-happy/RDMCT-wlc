import unittest
from optimality_runtime import certificate_asset_changes,reserve_for_growth


class AuditTests(unittest.TestCase):
    def test_only_reporting_helper_can_change(self):
        a={'JMS-version\\joint_model\\run_experiments.py':'b1ef110c2d205859d614d3588e99fbd99d3826b879c41891ae51e7b96a4635f6','model.py':'same'}
        b=dict(a);b['JMS-version\\joint_model\\run_experiments.py']='005259e5093256f925cf31ae83f4b9388b98810e009f692e8337f1156aadbfd1'
        self.assertEqual(len(certificate_asset_changes(a,b)),1)
        b['model.py']='modified'
        with self.assertRaises(ValueError):certificate_asset_changes(a,b)

    def test_inventory_change_rejected(self):
        with self.assertRaises(ValueError):certificate_asset_changes({'a':'1'}, {})

    def test_future_helper_changes_not_automatically_trusted(self):
        with self.assertRaises(ValueError):
            certificate_asset_changes({'JMS-version/joint_model/run_experiments.py':'a'},
                                      {'JMS-version/joint_model/run_experiments.py':'b'})

    def test_reserve_includes_active_and_external_growth(self):
        self.assertTrue(reserve_for_growth([],14000,6000,2048,4000))
        self.assertFalse(reserve_for_growth([1000],14000,6000,2048,4000))


if __name__=='__main__':unittest.main()
