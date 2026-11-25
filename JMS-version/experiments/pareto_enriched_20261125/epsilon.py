"""Focus ceiling solves on three integer-schedule changes using their independently checked parents."""
import sys
from native_caps import OUT,SQ,OLD,fixed

CASES={
    "early_fraction":(SQ/"fixed/short16/cap_811.75",[811.0625,811.125,811.1875,811.3125,811.4375,811.5625,811.6875,811.8125,811.875,811.9375]),
    "new_853":(OUT/"native/last_855_2/p_853_80_0",[840,844,847,848,849,850,851,851.5,852,852.25,852.5,852.75,853,853.25,853.5,853.75,854,854.25,854.5,854.75,855,857,865,885,920,965]),
    "new_855":(OUT/"neighbors/reassigned/cap_855",[848,850,851,852,852.5,853,853.125,853.25,853.375,853.5,853.625,853.75,853.875,854,854.125,854.25,854.375,854.5,854.625,854.75,854.875,855,856,860]),
    "center_979":(OUT/"neighbors/paired/cap_979",[965,970,974,975,976,977,978,978.25,978.5,978.75,979,979.25,979.5,979.75,980,981,983,986]),
}
if __name__=="__main__":
    fixed.sweep.CASES=CASES;fixed.sweep.OUT=OUT/"fixed"
    for key in CASES if len(sys.argv)==1 else [sys.argv[1]]:fixed.main(key)
