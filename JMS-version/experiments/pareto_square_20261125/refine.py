"""Refine newly discovered resource orders around observed changes in slope and large time gaps."""
import sys
from pathlib import Path
from fixed import OUT,main,sweep


if __name__=="__main__":
    new={
        "bridge16":(OUT/"native/dual_first_992/p_992_124_3",[843,868,894,918,939,960,976,986,992,1005,1032,1080,1140]),
        "jump_left16":(OUT/"native/p26_814/p_812_129_15",[812,812.125,812.375,812.75,813.5,814.5,816.5]),
        "jump_right16":(OUT/"native/p26_814/p_814_93_12",[812,812.5,813,813.25,813.5,813.75,814,815,819,830,860,920]),
    }
    sweep.CASES.update(new)
    for key in new:main(key)
