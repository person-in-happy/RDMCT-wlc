"""Re-evaluate all distinct frozen trajectories and check the eight-wafer sensitivity cases."""
from collections import defaultdict
import csv
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from score import DELTA_SECONDS, OBJECTIVE, metrics, square_penalty

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
ROOT = JMS.parent
OUT = JMS / "results" / HERE.name
POOL = JMS / "results/huber_residence_20261125/reuse/pool"

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def ranking(local, gamma):
    values = [(r["mean"]+square_penalty(r["D"])+gamma*r["E"],r) for r in local]
    best = min(v for v,_ in values)
    tied = [r for v,r in values if v <= best+1e-7]
    shortest = min(r["C"] for r in tied)
    winners = [r for r in tied if r["C"]<=shortest+2e-5]
    return dict(gamma=gamma,best=best,shortest_C=shortest,
                tied_trajectories=sorted(r["trajectory_sha256"] for r in winners),
                tied_E_values=sorted({r["E"] for r in winners}))

def main():
    manifest=read(POOL/"manifest.json")
    archive=POOL/"replayed.json"
    assert digest(archive)==manifest["files"][archive.name]
    trajectories={}
    for row in read(archive):
        trajectories.setdefault(row["trajectory_sha256"],row)
    groups=defaultdict(list)
    for row in trajectories.values():
        path=ROOT/row["source"]
        assert row["source_sha256"]==digest(path)
        doc=read(path)
        for token in row["location"].strip("/").split("/") if row["location"] else ():
            doc=doc[int(token) if isinstance(doc,list) else token]
        actual=metrics(doc)
        for a,b in (("mean_residence","mean"),("residence_range","D"),("clean_deficit","E"),("cmax","C")):
            assert abs(actual[a]-row[b])<0.00002
        groups[row["config_sha256"]].append(row)
    rankings=[]
    for config,rows in groups.items():
        tests=[ranking(rows,v) for v in (0,0.5,1,2)]
        same=all(set(t["tied_trajectories"])==set(tests[0]["tied_trajectories"]) for t in tests)
        rankings.append(dict(configuration=config,stable_optimal_set=same,grid=tests))
    cert=JMS/"results/residence_objective_20261125/best_reuse/continuous_frontier/certificate.json"
    family=read(cert)
    for group in family["native_replays"].values():
        assert group["exact_native_linear_rows"]==281012
        endpoints=[x["metrics"] for x in group["endpoints"]]
        assert [(x["cmax"],x["mean_residence"],x["residence_range"],x["clean_deficit"]) for x in endpoints]==[(553,3.25,1,0),(554,3.5,0,0)]
    scale=[]
    for delta in (Fraction(1,2),Fraction(1),Fraction(2)):
        spread=delta/4
        t=1-spread
        value=Fraction(13,4)+t/4+spread**2/(2*delta)
        assert value==Fraction(7,2)-delta/32
        scale.append(dict(delta=float(delta),C=float(553+t),spread=float(spread),global_H3=float(value)))
    changed=[x for x in rankings if not x["stable_optimal_set"]]
    summary=dict(objective=OBJECTIVE,delta_s=DELTA_SECONDS,trajectories=len(trajectories),groups=len(groups),
                 positive_E=sum(r["E"]>0 for r in trajectories.values()),changed_sets=len(changed),
                 unit_resolution=dict(points=[[553,3.75],[554,3.5]],positive_integer_spread_lower=3.625),
                 mean_bound_H3="mean + D/4 >= 3.5",delta_sweep=scale,affine_family_sha256=digest(cert),
                 physical_archive_sha256=digest(archive),rankings=rankings)
    (OUT/"sensitivity.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    print({k:summary[k] for k in ("trajectories","groups","positive_E","changed_sets")})
    for item in changed:
        print(item["configuration"], [(z["gamma"],z["tied_E_values"],z["shortest_C"],len(z["tied_trajectories"])) for z in item["grid"]])

if __name__=="__main__":
    main()
