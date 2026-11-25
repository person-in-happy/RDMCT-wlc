"""Finite-batch chamber quota objective with one terminal balance per installed chamber."""
import importlib.util
from functools import lru_cache
from pathlib import Path
from math import inf


_path=Path(__file__).resolve().parents[1]/"residence_objective_20261125/score.py"
_spec=importlib.util.spec_from_file_location("residence_event_reader",_path)
_residence=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_residence)


def metrics(schedule,range_weight=0.,clean_weight=1.):
    if range_weight!=0 or clean_weight<0:
        raise ValueError("The quota experiment uses zero range weight and a nonnegative quota weight")
    result=_residence.metrics(schedule)
    cfg=schedule["config"]
    clean=sum(cy["mode"]=="clean" for cy in schedule["cycles"])
    prod=len(schedule["cycles"])-clean
    quota=cfg["cleaning_interval"]*(clean+len(cfg["chambers"]))-prod
    result.update(production_count=prod,clean_count=clean,quota_unused=quota,
                  secondary=result["mean_residence"]+clean_weight*quota)
    return result


@lru_cache(maxsize=None)
def segment_lower(full,mixed,h,chambers,rotation,handling,gamma):
    """Count- and residence-relaxation DP; product times use the whole batch denominator."""
    n=full+mixed
    basic=2*rotation+2*handling
    costs={(0,0,0):0.}
    segments=[]
    for wafers in range(1,min(4,full)+1):
        segments.append((wafers,0,1,basic*max(0,wafers-2)))
    for pairs in range(1,min(mixed,h-1)+1):
        for wafers in range(pairs,min(2*pairs,mixed)+1):
            last=2 if wafers==2*pairs else 1
            segments.append((0,wafers,pairs+1,basic*wafers+handling*last))
    side={}
    for f in range(full+1):
        for b in range(mixed+1):
            for current in range(h):
                old=costs.get((f,b,current))
                if old is None:
                    continue
                side[f,b]=min(side.get((f,b),inf),old)
                for nf,nb,length,raw_residence in segments:
                    if f+nf>full or b+nb>mixed:
                        continue
                    for reset in ((False,True) if current else (False,)):
                        after=(0 if reset else current)+length
                        if after>h:
                            continue
                        mandatory=after==h
                        state=(f+nf,b+nb,0 if mandatory else after)
                        penalty=gamma*(h*(int(reset)+int(mandatory))-length)
                        value=old+raw_residence/n+penalty
                        costs[state]=min(costs.get(state,inf),value)
    if chambers==2:
        relaxed=min(side[f,b]+side[full-f,mixed-b] for f,b in side if (full-f,mixed-b) in side)
    elif chambers==1:
        relaxed=side[full,mixed]
    else:
        raise ValueError("Expected the manuscript one- or two-chamber model")
    return chambers*h*gamma+relaxed


def physical_lower(cfg,clean_weight=1.):
    f,m=(sum(port.get(mode,0) for port in cfg.load_ports.values()) for mode in ("4x1","2x2"))
    return segment_lower(f,m,cfg.cleaning_interval,len(cfg.chambers),cfg.rotation,cfg.handling,clean_weight)
