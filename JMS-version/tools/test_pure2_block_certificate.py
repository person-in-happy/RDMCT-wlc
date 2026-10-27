import unittest
from itertools import product
from pure2_block_certificate import block_certificate


class BlockTests(unittest.TestCase):
    def test_n16_h3_forces_full_blocks(self):
        b=block_certificate(16,2,3,90,500,1282,6)
        self.assertEqual((b['min_pairs'],b['max_pairs']),(4,4))
        self.assertEqual(b['forced_cycle_modes'],['2x2']*3+['clean']+['2x2']*3+['clean'])

    def test_h10_does_not_force_structure(self):
        b=block_certificate(16,2,10,90,500,789,8)
        self.assertIsNone(b['forced_cycle_modes'])
        self.assertEqual(b['max_nonterminal_cleanings'],0)

    def test_preserves_all_enumerated_count_options(self):
        for n,h,window,maxp in ((16,3,1282,6),(8,3,1000,6),(4,4,800,8),(16,10,789,8)):
            b=block_certificate(n,2,h,90,500,window,maxp)
            options=[(k,p) for k in range(1,h) for p in range(k+1,min(2*k,h)+1)]
            for blocks in range(1,4):
                for choices in product(options,repeat=blocks):
                    k=sum(t[0] for t in choices);p=sum(t[1] for t in choices);c=blocks-1
                    if k<b['min_pairs'] or k>n or p>maxp or p*90+c*500>window:continue
                    self.assertLessEqual(k,b['max_pairs'])
                    if b['min_pairs']:
                        self.assertLessEqual(b['min_nonterminal_cleanings'],c)
                        self.assertLessEqual(c,b['max_nonterminal_cleanings'])
                        self.assertLessEqual(b['min_productive'],p)
                        self.assertLessEqual(p,b['max_productive'])
                    if b['forced_cycle_modes']:
                        self.assertTrue(all(q==h for _,q in choices))


if __name__=='__main__':unittest.main()
