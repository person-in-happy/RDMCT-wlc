"""Recover witnesses for every pooled nondominated discovery, including non-exported interiors."""
from collections import defaultdict
import gzip
import json
import sys
import time

from campaign75 import OUT, audit_schedule, pool, status
from large75 import METHODS, SEEDS, BUDGET, Search, read, save, signature


def front(points):
    accepted = []
    for a,b in sorted(set(tuple(x) for x in points)):
        if not accepted or b < accepted[-1][1]:
            accepted.append((a,b))
    return accepted


class Collected(Exception):
    pass


def reconstruct(task):
    method,seed,requested = task
    dest = OUT/"pooled"
    wanted = set(requested)

    class Replay(Search):
        def admit(self, data, genes, end, cap=None):
            point = super().admit(data,genes,end,cap)
            if point not in wanted:
                return point
            sig = signature(data)
            path = dest/(sig+".json.gz")
            with gzip.open(path,"wt",encoding="utf-8") as stream:
                json.dump(data,stream,ensure_ascii=False,allow_nan=False)
            source = dict(a=point[0],b=point[1],schedule_sha256=sig,file=str(path.relative_to(OUT)),
                          method=method,seed=seed,genes=genes)
            save(dest/f"witness_{point[0]}_{point[1]}.json",source)
            wanted.remove(point)
            if not wanted:
                raise Collected
            return point
    try:
        Replay(seed).run(method,BUDGET*1.6)
    except Collected:
        pass
    if wanted:
        raise RuntimeError(f"Original discovery not reproduced: {wanted}")
    return len(requested)


def recover(witness_only=False):
    dest = OUT/"pooled"
    dest.mkdir(exist_ok=True)
    if not witness_only:
        assert (OUT/"complete.json").exists()
    runs = {(m,s):read(OUT/f"{m}_{s}"/"run.json") for m in METHODS for s in SEEDS}
    union = front(p for r in runs.values() for p in r["internal_nondominated"])
    witnesses,owners = {},defaultdict(list)
    for (m,s),r in runs.items():
        for x in r["archive"]:
            k = (x["a"],x["b"])
            if k in union:
                witnesses.setdefault(k,dict(a=k[0],b=k[1],schedule_sha256=x["schedule_sha256"],
                    file=f"{m}_{s}/"+x["file"],method=m,seed=s,genes=x["genes"]))
        for t,a,b in r["trace"]:
            if (a,b) in union:
                owners[a,b].append((t,m,s))
    missing = defaultdict(list)
    for p in union:
        if p in witnesses:
            continue
        path = dest/f"witness_{p[0]}_{p[1]}.json"
        if not path.exists():
            t,m,s = min(owners[p])
            assert t <= BUDGET
            missing[m,s].append(p)
    tasks = [(m,s,ps) for (m,s),ps in missing.items()]
    status(f"Complete observed union: {len(union)} nondominated coordinates; {sum(map(len,missing.values()))} interior schedules to reconstruct from in-budget discoveries")
    pool("witness recovery",tasks,reconstruct,lambda item,value:None,BUDGET)
    if witness_only:
        return
    for p in union:
        if p not in witnesses:
            witnesses[p] = read(dest/f"witness_{p[0]}_{p[1]}.json")
        row = witnesses[p]
        row["observed_in"] = [dict(method=m,seed=s,admitted_s=t) for t,m,s in owners[p]]
    audit = OUT/"row_audit"
    paths = [OUT/r["file"] for r in witnesses.values() if not (audit/(r["schedule_sha256"]+".json")).exists()]
    pool("pooled original rows",paths,audit_schedule,lambda item,val:save(audit/(val["schedule"]+".json"),val),25)
    for p in union:
        row = witnesses[p]
        ck = read(audit/(row["schedule_sha256"]+".json"))
        assert (ck["metrics"]["cmax"],ck["secondary_original"]) == p
    save(dest/"front.json",[witnesses[p] for p in union])
    status(f"FULL OBSERVED UNION VERIFIED: {len(union)} schedules")


if __name__ == "__main__":
    recover("--witness-only" in sys.argv[1:])
