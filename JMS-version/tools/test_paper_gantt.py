"""Test the scientific claim gate, without running an optimizer."""
import copy
import unittest
from render_optional_cleaning_gantt import optimality_errors, wafer_rows


class OptimalityGateTests(unittest.TestCase):
    def setUp(self):
        self.physical = {'valid': True, 'product_return_cmax': 100.0}
        self.data = dict(primary_status='optimal', experiment_scope='joint',
                         full_candidate_space=True, restricted_candidate_bounds=False,
                         original_model_check=True, primary_bound=100.0, primary_gap=0.0)

    def test_closed_full_model_primary_bound(self):
        self.assertEqual(optimality_errors(self.data, self.physical), [])

    def test_reject_timeout_even_with_equal_bounds(self):
        self.data['primary_status'] = 'timelimit'
        self.assertTrue(optimality_errors(self.data, self.physical))

    def test_reject_conditional_or_restricted_optimum(self):
        for change in ({'experiment_scope': 'fixed_configuration'},
                       {'full_candidate_space': False}, {'restricted_candidate_bounds': True}):
            self.assertTrue(optimality_errors(self.data | change, self.physical))

    def test_reject_weak_missing_and_sentinel_bounds(self):
        for bound in (39, None, -1e20, float('nan')):
            self.assertTrue(optimality_errors(self.data | {'primary_bound': bound}, self.physical))

    def test_secondary_optimum_does_not_certify_primary(self):
        self.data.update(status='optimal', primary_status='timelimit')
        self.assertTrue(optimality_errors(self.data, self.physical))

    def test_invalid_replay_is_rejected(self):
        self.assertTrue(optimality_errors(self.data, self.physical | {'valid': False}))


class WaferFlowTests(unittest.TestCase):
    def setUp(self):
        kinds = ['origin_pick', 'al_put', 'al_pick', 'upper_put',
                 'source_pick', 'destination_put', 'lower_pick', 'origin_put']
        intervals = [(0, 1), (3, 4), (8, 9), (11, 12), (15, 16), (33, 34), (38, 39), (42, 43)]
        self.data = {
            'jobs': [dict(name='W1', product=True, pair=0, loan_start=0, loan_end=43,
                          load_end=20, unload_start=30)],
            'events': [dict(job='W1', kind=k, start=s, end=e) for k, (s, e) in zip(kinds, intervals)],
            'cycles': [dict(pairs=[0, 1], mode='4x1', start=22, end=28)],
        }

    def test_continuous_material_lifecycle_and_true_processing_length(self):
        rows = wafer_rows(self.data)
        self.assertEqual(rows[0][1], 0)
        self.assertEqual(rows[-1][2], 43)
        self.assertTrue(all(a[2] == b[1] for a, b in zip(rows, rows[1:])))
        self.assertEqual(sum(e-s for _, s, e, k in rows if k == '加工'), 6)
        self.assertEqual(sum(e-s for _, s, e, _ in rows), 43)

    def test_invalid_processing_outside_chamber_is_rejected(self):
        invalid = copy.deepcopy(self.data)
        invalid['cycles'][0]['end'] = 32
        with self.assertRaises(ValueError):
            wafer_rows(invalid)


if __name__ == '__main__':
    unittest.main()
