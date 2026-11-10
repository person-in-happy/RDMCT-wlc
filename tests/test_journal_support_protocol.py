"""Protocol regression tests; no optimization or policy training."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'JMS-version/tools'))
import journal_support_experiments as j


class SupportProtocolTests(unittest.TestCase):
    def test_prespecified_coverage_and_no_capacity_truncation(self):
        cases = j.test_cases()
        self.assertEqual(27, len({j.config_key(cfg) for _, cfg in cases}))
        for _, cfg in cases + j.mechanism_cases():
            j.base.config_check(cfg)
            self.assertEqual(cfg['source'], 'dual')
            self.assertEqual(cfg['full_time'], 2 * cfg['mix_time'])
        self.assertEqual(24, len(j.mechanism_cases()))

    def test_backfill_reuses_instead_of_repeating_scip_and_t1(self):
        cells, _ = j.plan(SimpleNamespace(suite='backfill_standard'))
        self.assertEqual(len(cells), 96)
        self.assertEqual(len({c['id'] for c in cells}), 96)
        self.assertEqual({c['training_seed'] for c in cells}, {2, 3})
        self.assertNotIn('scip', {c['method'] for c in cells})

    def test_mechanism_has_paired_rules_and_common_input(self):
        cells, _ = j.plan(SimpleNamespace(suite='mechanism'))
        self.assertEqual(144, len(cells))
        for c in cells[::2]:
            d = cells[cells.index(c)+1]
            self.assertEqual(c['config_data'], d['config_data'])
            self.assertEqual(c.get('values'), d.get('values'))
            self.assertEqual((c['arm'], d['arm']), ('optional', 'legacy'))

    def test_known_coupling_is_not_a_rhythm_witness(self):
        d = j.read(j.base.SMALL / 'runs/n1_H2_2x2_dual__s1__scip/result.json')
        m = j.metrics(d)
        self.assertTrue(m['coupled_witness'])
        self.assertEqual((m['auxiliary_loans'], m['distinct_auxiliaries'], m['repeat_loans'], m['peak_auxiliary_loans']), (9, 7, 2, 5))
        self.assertEqual(m['rhythm_centers'], 0)

    def test_transfer_shares_spbs_across_policies(self):
        source = j.base.SMALL / 'runs/n1_H2_2x2_dual__s1__scip'
        cfg = j.read(source / 'result.json')['config']
        with patch.object(j, 'parent_sources', return_value=({'case': ('cfg', str(source/'result.json'), str(source/'variables.json'))}, {})), patch.object(j, 'read', return_value=cfg):
            cells, _ = j.plan(SimpleNamespace(suite='transfer', source_campaign='fixture'))
        self.assertEqual(len(cells), 72)
        self.assertEqual(sum(c['arm']=='shared_spbs' for c in cells), 3)
        self.assertEqual(sum(c['method']=='scip' and c['arm']!='shared_spbs' for c in cells), 6)

    def test_timeout_without_incumbent_is_retained_not_infeasible(self):
        cfg = j.test_cases()[0][1]
        data = dict(solutions=0, primary_status='timelimit', primary_bound=-1e20, primary_gap=1e20, solve_seconds=300)
        cell = dict(config='config.json', seed=17, arm='qualification')
        def read_fixture(path):
            return cfg if str(path)=='config.json' else data
        with patch.object(j, 'read', side_effect=read_fixture), patch.object(j.base, 'solve'), patch.object(j.shutil, 'copy2'):
            e = j.basic_run(cell, Path('not-created'), dict(time_limit=300, memory_mb=8796093022207.), 'qualification', False)
        self.assertFalse(e['valid'])
        self.assertEqual(e['state'], 'timelimit')
        self.assertIsNone(e['primary_bound'])
        self.assertIsNone(e['primary_gap'])

    def test_seed_replication_does_not_create_extra_instances(self):
        rows = []
        for case, gain in [('a', 10), ('b', -5)]:
            for seed in (1, 2, 3):
                for training in (1, 2, 3):
                    for arm, value in [('hem_spbs', 100), ('proposed_spbs', 100-gain)]:
                        rows.append(dict(case=case, seed=seed, training_seed=training, arm=arm, valid=True, metrics={'product_cmax': value}))
        r = j.contrasts(rows)[0]
        self.assertEqual(r['instances'], 2)
        self.assertAlmostEqual(r['mean_relative_gain_percent'], 2.5)
        self.assertEqual((r['wins'], r['losses']), (1, 1))
        rows[-1]['valid'] = False
        self.assertEqual(j.contrasts(rows)[0]['instances'], 1)  # never pair unmatched successes


if __name__ == '__main__':
    unittest.main()
