import unittest
from types import SimpleNamespace
from incumbent_sublevel import capacity_certificate

class SublevelBoundsTests(unittest.TestCase):
    def cfg(self, mode, n=16):
        return SimpleNamespace(load_ports={'LP1':{mode:n}},max_pairs=0,max_cycles=0,
             chambers=(1,2),full_time=180,mix_time=90,cleaning_time=500,cleaning_interval=3,
             atr_handling=4,atr_travel=3,alignment=20,pump=30,handling=1,vtr_travel=2,vent=25)

    def test_950_full_mode_capacity(self):
        c=capacity_certificate(self.cfg('4x1'),950)
        self.assertEqual((c['pairs'],c['cycles_per_chamber'],c['total_cycles']),(16,4,8))
        self.assertEqual((c['route_lead'],c['route_tail']),(76,40))

    def test_mixed_pairs_subtract_exact_double_occurrences(self):
        cfg=self.cfg('2x2');cfg.cleaning_interval=10
        c=capacity_certificate(cfg,905)
        self.assertEqual((c['pairs'],c['cycles_per_chamber'],c['total_cycles']),(28,9,18))

    def test_enumerate_cycle_counts_with_terminal_cleaning(self):
        for mode in ('4x1','2x2'):
            cfg=self.cfg(mode,4);d=cfg.full_time if mode=='4x1' else cfg.mix_time
            for upper in (360,500,720,950,1400):
                cert=capacity_certificate(cfg,upper)
                options=[]
                for productive in range(1,9 if mode=='2x2' else 5):
                    for nonterminal in range((productive-1)//cfg.cleaning_interval,productive):
                        if productive*d+nonterminal*500 > upper-116:continue
                        for terminal in (0,1):options.append((productive,nonterminal+terminal))
                for p1,c1 in options:
                    for p2,c2 in options:
                        if p1+p2 > (8 if mode=='2x2' else 4):continue
                        self.assertLessEqual(max(p1+c1,p2+c2),cert['cycles_per_chamber'])
                        self.assertLessEqual(p1+p2+c1+c2,cert['total_cycles'])

    def test_reject_restricted_source(self):
        cfg=self.cfg('4x1');cfg.max_pairs=8
        with self.assertRaises(ValueError):capacity_certificate(cfg,950)

if __name__=='__main__':unittest.main()
