"""Checks of comparison design, pairing and deadline acceptance."""
import unittest
import formal_ablation as f


class FormalDesignTests(unittest.TestCase):
    def setUp(self):
        self.cases = f.source_records()
        self.cells = f.make_cells(self.cases)

    def test_complete_design_and_no_fake_scip_training_repeats(self):
        self.assertEqual(len(self.cells), 1224)
        self.assertEqual(len({c['id'] for c in self.cells}), 1224)
        self.assertEqual(sum(c['suite'] == 'preparation' for c in self.cells), 51)
        self.assertEqual(sum(c['budget'] for c in self.cells), 70 * 3600)
        self.assertEqual(sum(c['optimal_control'] for c in self.cases), 1)
        self.assertTrue(all(c['training_seed'] == 0 for c in self.cells if c['method'] == 'scip'))
        self.assertEqual({c['seed'] for c in self.cells}, {11, 12, 13})

    def test_shared_initialization_and_equal_total_budget(self):
        lookup = {c['id']: c for c in self.cells}
        for cell in self.cells:
            if cell['suite'] == 'preparation':
                continue
            self.assertAlmostEqual(cell['budget'] + cell['init_budget'], cell['total_budget'])
            if cell['with_spbs']:
                prep = lookup[cell['preparation']]
                self.assertEqual((cell['case'], cell['seed'], cell['total_budget']),
                                 (prep['case'], prep['seed'], prep['total_budget']))
                self.assertEqual(cell['init_budget'], prep['budget'])
        self.assertTrue(all(c['total_budget'] == 900 for c in self.cells if c['group'] == 'expansion'))

    def test_deadline_rejects_late_solver_and_late_extraction(self):
        self.assertTrue(f.timely(48, 48, 60, 60))
        self.assertFalse(f.timely(48.01, 48, 60, 60))
        self.assertFalse(f.timely(47, 48, 60.01, 60))

    def test_pairs_preserve_all_outcomes_and_missing_partners(self):
        selected = [c for c in self.cells if c['case'] == 'n2_mixed_scenario2' and
                    c['total_budget'] == 60 and c['seed'] == 11]
        observations = []
        for c in selected:
            if c['arm'] == 'scip_spbs':
                observations.append(c | dict(valid=True, budget_eligible=True, metrics={'cmax': 500.}))
            if c['arm'] == 'proposed_spbs':
                observations.append(c | dict(valid=True, budget_eligible=True,
                    metrics={'cmax': {1: 499., 2: 500., 3: 501.}[c['training_seed']]}))
        pairs = f.paired_rows({'cells': selected}, observations)
        comparison = [p for p in pairs if p['contrast'] == 'full_vs_scip_spbs']
        self.assertEqual([p['outcome'] for p in comparison], ['win', 'tie', 'loss'])
        self.assertEqual(len({p['right'] for p in comparison}), 1)
        self.assertTrue(all(not p['complete'] for p in pairs if p['contrast'] == 'full_vs_hem_spbs'))

    def test_spbs_neighborhoods_release_expected_variables(self):
        self.assertFalse(f.spbs_fixed('sync_a', 1, {'vtr_a'}))
        self.assertTrue(f.spbs_fixed('order_vtr_a_b', 1, {'vtr_a'}))
        self.assertFalse(f.spbs_fixed('order_vtr_a_b', 2, {'vtr_a'}))
        self.assertTrue(f.spbs_fixed('order_U_a_b', 2, set()))
        self.assertFalse(f.spbs_fixed('order_U_a_b', 3, set()))
        self.assertFalse(f.spbs_fixed('order_ATR_a_b', 4, set()))
        self.assertTrue(f.spbs_fixed('jp_a_b', 5, set()))
        self.assertFalse(f.spbs_fixed('slot_a', 5, set()))


if __name__ == '__main__':
    unittest.main()
