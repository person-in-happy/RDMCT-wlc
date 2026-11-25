"""Propagate resource reuse and route precedence on the order statistics of every product."""
import hashlib
import itertools
import json
from pathlib import Path

import tool_partition as tool

HERE=Path(__file__).resolve()
physical=tool.exact_sides
ancestor=tool.inherited
original_dir=tool.cache_dir


def rank_propagation(m,v,pattern,cap,moves):
    physical(m,v,pattern,cap,moves)
    n=len(pattern)
    assert n==16
    stages=("al","ap","up","sp","ld","ul","dp","lp","origin_put")
    durations=(24,7,34,3,181,3,26,7)
    forward=[7]
    for lag in durations:forward.append(forward[-1]+lag)
    tails=[0]*len(stages);tails[-1]=4
    for j in reversed(range(len(durations))):
        tails[j]=tails[j+1]+durations[j]
    # A repeated use of one LL slot separates both its starts and its completed pickups.
    resets={"al":(1,28),"ap":(1,28),"up":(2,65),"sp":(2,65),"dp":(2,55),"lp":(2,55)}
    sorted_={}
    for j,stage in enumerate(stages):
        values=[v[f"{stage}_{i}"] for i in range(n)]
        # A sorting network avoids enumerating the permutations of simultaneous paired events.
        width=2
        while width<=n:
            stride=width//2
            while stride:
                for i in range(n):
                    other=i^stride
                    if i>=other:continue
                    small=m.new_int_var(forward[j],cap-tails[j],"")
                    large=m.new_int_var(forward[j],cap-tails[j],"")
                    m.add_min_equality(small,[values[i],values[other]])
                    m.add_max_equality(large,[values[i],values[other]])
                    if i&width:values[i],values[other]=large,small
                    else:values[i],values[other]=small,large
                stride//=2
            width*=2
        sorted_[stage]=values
        if stage in resets:
            step,lag=resets[stage]
            for i in range(step,n):
                m.add(values[i]>=values[i-step]+lag)
        if j:
            for i in range(n):
                m.add(values[i]>=sorted_[stages[j-1]][i]+durations[j-1])
        for i in range(n-1):
            m.add(values[i]<=values[i+1])


def run():
    import argparse
    p=argparse.ArgumentParser();p.add_argument("kind");p.add_argument("cap",type=int)
    p.add_argument("--vault",action="store_true");p.add_argument("--budget",type=int,default=30)
    p.add_argument("--workers",type=int,default=2);p.add_argument("--index",type=int)
    opts=p.parse_args()
    assert opts.vault
    # Run the same exhaustive solver in its own namespace. Each process sees just one model.
    tool.HERE=HERE
    tool.cache_dir=lambda kind,cap,treatment:original_dir(kind,cap,"ranked")
    tool.exact_sides=rank_propagation
    if opts.index is None:
        tool.controller(opts.kind,opts.cap,opts.budget,opts.workers,True)
    else:
        tool.worker(opts.kind,opts.cap,opts.budget,opts.index,True)
    directory=tool.cache_dir(opts.kind,opts.cap,"ranked")
    if opts.index is None:
        tool.atom(directory/"implementation.json",{
            p:hashlib.sha256(HERE.with_name(p).read_bytes()).hexdigest() for p in
            ("rank_partition.py","tool_partition.py","partition.py","port_projection.py","ordered_projection.py","batch_lower.py")})


if __name__=="__main__":
    run()
