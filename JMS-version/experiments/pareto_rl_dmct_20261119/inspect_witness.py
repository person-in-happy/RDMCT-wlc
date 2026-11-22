"""Identify the exact original rows preventing reconstruction of a returned timetable."""
import argparse
import gzip
import json
from pathlib import Path

from common import config, metrics
from native import Native
from validate import validate
from witness import sparse_witness


def diagnose(case, paths):
    native=Native(config(case),1,25)
    try:
        for path in paths:
            with gzip.open(path,"rt",encoding="utf-8") as f:
                d=json.load(f)
            checked=native.warm(d)
            print(path.name, "A",d["cmax"],"B",metrics(d,25)["secondary"],
                  "physical",validate(d)["valid"],"original",checked,flush=True)
            if checked:
                continue
            native.m.hideOutput(False)
            values=sparse_witness(native.x.cfg,d)
            sol=native.m.createSol()
            for var in native.variables:
                if var.name in values:
                    native.m.setSolVal(sol,var,float(values[var.name]))
            native.m.checkSol(sol,printreason=True,completely=False,original=True)
            native.m.freeSol(sol)
    finally:
        native.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    parser.add_argument("folder",type=Path)
    args=parser.parse_args()
    diagnose(args.case,sorted(args.folder.glob("point_*.json.gz")))
