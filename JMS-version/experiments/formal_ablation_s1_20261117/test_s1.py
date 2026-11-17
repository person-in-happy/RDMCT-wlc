import unittest
from unittest.mock import patch
import s1_ablation as s
import qualify_s1 as q


class S1DesignTests(unittest.TestCase):
    def test_s1_cases_and_300_second_matched_design(self):
        cases = [dict(case=n, backend='D', group='main', optimal_control=False, budgets=[300]) for n in s.CASES]
        with patch.object(s.f, 'SEEDS', (1, 2, 3)):
            cells = s.f.make_cells(cases)
        self.assertEqual(len(cells), 144)
        self.assertEqual(sum(c['suite']=='preparation' for c in cells), 6)
        self.assertEqual(sum(c['budget'] for c in cells), 36000)
        self.assertEqual({c['seed'] for c in cells}, {1,2,3})
        for cell in cells:
            if cell['suite']=='ablation':
                self.assertEqual(cell['budget']+cell['init_budget'], 300)

    def test_structures_include_mandatory_terminal_cleaning(self):
        for case in q.CASES:
            for alternative in (False, True):
                pairs, cycles = q.specification(case, alternative)
                counts = {}
                for (chamber,index),(mode,occupants,front) in sorted(cycles.items()):
                    self.assertEqual(len(occupants), 2)
                    self.assertIn(front, occupants)
                    self.assertTrue(all(pairs[p][0]==mode and pairs[p][1]==chamber for p in occupants))
                    counts[chamber] = 0 if mode=='clean' else counts.get(chamber,0)+1
                    self.assertLessEqual(counts[chamber],2)
                    if counts[chamber]==2:
                        self.assertEqual(cycles[chamber,index+1][0], 'clean')
                for p, (mode,_,members) in pairs.items():
                    if members:
                        occupancy=sum(p in c[1] for c in cycles.values())
                        self.assertEqual(occupancy,2 if mode=='2x2' else 1)

    def test_resource_exception_only_removes_existing_idle_controller(self):
        with patch.object(s, 'ORIGINAL_FOREIGN', return_value=[10,11,12]), \
             patch.object(s, 'existing_idle_controller', side_effect=lambda pid: pid==10):
            self.assertEqual(s.coordinated_foreign({99}),[11,12])


if __name__=='__main__':
    unittest.main()
