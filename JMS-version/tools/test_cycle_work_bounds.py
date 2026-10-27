import unittest
from itertools import product
from cycle_work_bounds import double_exposure_work


class WorkTests(unittest.TestCase):
    def test_n16_h3_bound(self):
        self.assertEqual(double_exposure_work(4,3,90,500),(6,1,1040))
        self.assertEqual(76+40+double_exposure_work(4,3,90,500)[2],1156)

    def test_enumerated_nonempty_blocks(self):
        for h in (2,3,4,5):
            for count in range(1,5):
                for sizes in product(range(1,h),repeat=count):
                    k=sum(sizes)
                    actual=(k+count)*90+(count-1)*500
                    self.assertLessEqual(double_exposure_work(k,h,90,500)[2],actual)

    def test_h10_no_intermediate_clean_needed_in_bound(self):
        self.assertEqual(double_exposure_work(4,10,90,500),(5,0,450))


if __name__=='__main__':unittest.main()
