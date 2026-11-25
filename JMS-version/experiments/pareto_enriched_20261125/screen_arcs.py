"""Lift alternative integer-score witnesses and test their timing flexibility on the native objective."""
import sys
from pathlib import Path
from native_caps import OUT,fixed
import native
from support import read,write

SOURCES={
    "cross873":("full_first_877_0","p_873_50_1",[850,855,860,865,868,870,871,872,872.25,872.5,872.75,873,873.125,873.25,873.375,873.5,873.625,874,875,879,886,895]),
    "cross875":("full_first_877_0","p_875_56_0",[854,860,865,869,870,871,872,873,873.5,874,874.25,874.5,874.75,875,875.25,875.5,876,878,885]),
    "cross864":("last_refined_875_2","p_864_64_0",[848,850,852,853,854,855,856,857,858,860,861,862,863,863.25,863.5,863.75,864,864.25,864.5,865,870,880]),
    "cross883":("last_refined_905_2","p_883_56_0",[849,852,855,858,860,865,870,875,880,881,882,882.25,882.5,882.75,883,883.25,883.5,884,890,910]),
}


def candidates():
    selected=[]
    for parent,key,_ in SOURCES.values():
        p=OUT/"search"/parent/(key+".json")
        d=native.reconstruct(read(p));assert native.attach_hands(d) and native.validate(d)["valid"]
        selected.append((p,d,fixed.metrics(d)))
    return selected,[],len(selected)


if __name__=="__main__":
    native.OUT=OUT
    if len(sys.argv)==1:
        native.checked_candidates=candidates;native.main()
    else:
        key=sys.argv[1];parent,record,caps=SOURCES[key]
        fixed.sweep.CASES={key:(OUT/"native"/parent/record,caps)};fixed.sweep.OUT=OUT/"fixed"
        fixed.main(key)
