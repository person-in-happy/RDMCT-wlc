"""Prepare one common starting timetable per 75-wafer workload, independently of trial seeds."""
from collections import Counter
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "pareto75_thesis_20261119"
sys.path.insert(0,str(OLD))
from large75 import (Config, GridTiming, Packing, Placement, Retiming, Routes, Search, PARETO,
                     SOURCE, digest, lower_bound, metrics, read, save, signature, validate)
from common import ROOT

OUT = HERE/"results"/"paired01"
CASES = ("mix37","mix50")
METHODS = ("domain","uniform","nsga2","moead")
SEEDS = tuple(range(101,113))
NFE = 160
WORKERS = 6
EXPORT = 7
PORTS50 = ((13,6),(13,6),(12,7),(12,6))


def load_schedule(path):
    with gzip.open(path,"rt",encoding="utf-8") as stream:
        return json.load(stream)


def save_schedule(path,data):
    temp=path.with_suffix(".pending")
    with gzip.open(temp,"wt",encoding="utf-8",compresslevel=3) as stream:
        json.dump(data,stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
    temp.replace(path)


def prepare():
    target=OUT/"shared"
    target.mkdir(parents=True,exist_ok=True)
    for case in CASES:
        spec=target/(case+".json")
        if spec.exists():
            old=read(spec)
            assert signature(load_schedule(target/old["file"]))==old["sig"]
            continue
        t=time.monotonic()
        if case=="mix37":
            routes=Routes()
            cfg,plan,warm=routes.cfg,routes.plan,routes.warm
        else:
            cfg=Config(load_ports={f"LP{i}":{"4x1":a,"2x2":b} for i,(a,b) in enumerate(PORTS50,1)})
            packing=Packing(cfg)
            beam=[()]
            for k in range(packing.n):
                beam=packing.advance(beam,24)
                spent=time.monotonic()-t
                print(f"50+25 common beam: {k+1}/{packing.n} blocks, failed 0, ETA {spent*(packing.n-k-1)/(k+1):.0f}s",flush=True)
            for plan in beam:
                warm=Retiming(GridTiming(packing,plan),25).solve("A",None,120)
                if warm:
                    break
            else:
                raise RuntimeError("No feasible common timetable in the final beam")
        assert validate(warm)["valid"]
        sig=signature(warm)
        path=target/(sig+".json.gz")
        save_schedule(path,warm)
        m=metrics(warm,25)
        save(spec,dict(case=case,config=asdict(cfg),plan=plan,file=path.name,sig=sig,
                       a=m["cmax"],b=m["secondary"],elapsed=time.monotonic()-t,
                       bounds=[[0,1.5*m["cmax"]],[0,2*m["secondary"]]]))
        print(f"{case} frozen reference: A={m['cmax']}, B={m['secondary']}",flush=True)


class CaseRoutes(Routes):
    def __init__(self,case):
        info=read(OUT/"shared"/(case+".json"))
        self.cfg=Config(**info["config"])
        self.base=Packing(self.cfg)
        self.plan=tuple(tuple(row) for row in info["plan"])
        self.order=[(k,ch) for k,ch,_ in self.plan if k<self.base.n]
        self.groups=self.base.groups
        self.n=self.base.n
        assert sorted(k for k,ch in self.order)==list(range(self.n))
        self.place=Placement(self.cfg,{})
        self.lookup={w:k for k,(_,wafers) in enumerate(self.groups) for w in wafers}
        self.initial=(0,0,0,0)
        self.limits=(6,)+(1+6*self.n,)*3
        self.preset=((0,0),(1,1),(2,1),(3,1),(3,3))
        self.warm=load_schedule(OUT/"shared"/info["file"])
        assert signature(self.warm)==info["sig"]
        self.ab=(info["a"],info["b"])


if __name__=="__main__":
    prepare()
