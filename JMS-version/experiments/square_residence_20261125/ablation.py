"""Audit paired budgets and transfer only ablation runs whose archived ranking is conclusive."""
from collections import defaultdict
import argparse
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from statistics import mean, stdev
from score import OBJECTIVE, metrics

JMS = Path(__file__).resolve().parents[2]
HUB = JMS/"results/huber_residence_20261125"
OUT = JMS/"results/square_residence_20261125/table5"
EPS = 2e-4
ARMS = ("full","no_rerank","no_spbs","hem","scip_default")

def digest(p):
    return sha256(p.read_bytes()).hexdigest()

def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def one_pair_per_recipe(schedule):
    modes = {p["id"]:p["mode"] for p in schedule["config"]["pjobs"]}
    groups = defaultdict(set)
    for job in schedule["jobs"]:
        if job["product"]:
            groups[modes[job["pjob"]]].add(job["pair"])
    return len(groups)==2 and all(len(pairs)==1 for pairs in groups.values())

def compare(x,y):
    assert abs(float(x)-float(y))<=EPS,(x,y)

def write(name, rows):
    with (OUT/name).open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def evidence(seed,arm,previous,ref):
    if arm=="full":
        folder=HUB/f"runs/ref5_{seed}"
        pos=folder/"B"
        b=read(pos/"result.json")
        clock=read(folder/"timing.json")
        assert b["proof"]["identically_zero_D"] and clock["new_B_sha256"]==digest(pos/"result.json")
        reason="Both objectives agree for every retiming on this handoff (one product pair per recipe); A and measured timing retained."
        report=previous
        native=b["replayed_rows"]
        assert b["files"]["schedule.json"]==digest(pos/"schedule.json") and b["files"]["assignment.json.gz"]==digest(pos/"assignment.json.gz")
        assert b["replay"]["valid"]
        check=pos/"result.json"
        compare(clock["total_s"],report["used_s"])
        compare(clock["total_s"],sum(clock[k] for k in ("prep_seconds","A_seconds","B_wall_seconds")))
    else:
        fresh=(seed,arm)==(2,"no_spbs")
        folder=OUT/"s2_no_spbs" if fresh else HUB/f"runs/t5_{seed}_{arm}"
        if not (folder/"result.json").is_file(): return None
        pos=folder/"endpoint"
        report=read(folder/"result.json")
        check=pos/"primary.json"
        native=read(check)["rows"]
        assert read(check)["replay"]["valid"] and native>0
        assert report["schedule_sha256"]==digest(pos/"schedule.json")
        assert report["assignment_sha256"]==digest(pos/"assignment.json.gz")
        compare(report["reference_s"],ref["used_s"])
        compare(report["reference_f_A"],ref["f_A"])
        compare(report["reference_f_B"],ref["f_B"])
        schedule=read(pos/"schedule.json")
        f=metrics(schedule)
        if fresh:
            reason="New original-model paired solve using the quadratic score for all incumbents and for early stopping."
            compare(f["secondary"],report["f_B"])
        else:
            assert report["f_A"]>float(ref["f_A"])+EPS
            if report["stage"]=="B":
                assert one_pair_per_recipe(schedule)
                proof=read(folder/"A_reuse.json")
                assert proof["orig_A_proof"]
                reason="Same handoff and budget; one product pair per recipe makes the secondary objective identical for every feasible retiming."
            elif f["residence_range"]<=1+1e-7:
                compare(f["secondary"],report["f_B"])
                reason="Unchanged primary search. The old best tied-makespan score is a lower bound on every quadratic score, attained by the same endpoint."
            else:
                assert (seed,arm)==(1,"hem")
                parent=JMS/read(folder/"A_reuse.json")["source"]
                log=parent/"A_attempt1/solver.log"
                count=int(re.findall(r"Primal Bound\s*:[^\n]*\((\d+) solutions?\)",log.read_text(errors="replace"))[-1])
                files=sorted(parent.glob("witness*.json.gz"))
                vals=[json.load(gzip.open(q,"rt"))["nonzero"] for q in files]
                assert len(files)+1==count==3 and vals[0]!=vals[1]
                assert sum(abs(a["Cmax"]-f["cmax"])<=EPS for a in vals)==1
                assert min(a["Cmax"] for a in vals)>=f["cmax"]-EPS
                warm=JMS/"results/table5_one_percent_20261124/runs/s1_full"
                # Accepted original warm start has C=406 s, above both recorded improvements.
                initial=read(parent/"result.json")["key"]["start"]
                oldinputs=read(JMS/"results/table5_one_percent_20261124/protocol.json")
                assert initial==oldinputs["inputs"]["1/full"]
                other=read(HUB/"runs/t5_1_no_rerank/result.json")
                assert initial==other["key"]["start"] and other["f_A"]>f["cmax"]+EPS
                reason="Complete primary pool of three (common initial schedule and two accepted improvements); only one accepted schedule has the smallest makespan."
    schedule=read(pos/"schedule.json")
    f=metrics(schedule)
    if arm=="full":
        assert one_pair_per_recipe(schedule)
        compare(f["secondary"],previous["f_B"])
    compare(report["f_A"],f["cmax"])
    if arm!="full":
        hit=f["cmax"]<=float(ref["f_A"])+EPS and f["secondary"]<=float(ref["f_B"])+EPS
        assert (report["reason"]=="target")==hit
    return dict(seed=seed,arm=arm,f_A=f["cmax"],f_B=f["secondary"],mean_residence=f["mean_residence"],
                spread=f["residence_range"],E=f["clean_deficit"],used_s=float(report["used_s"]),
                budget_s=float(ref["used_s"]),cut_rounds=int(report["calls"]),reason=reason,
                rows=native,source=pos.relative_to(JMS).as_posix(),schedule_sha256=digest(pos/"schedule.json"),
                assignment_sha256=digest(pos/"assignment.json.gz"),certificate_sha256=digest(check))

def main(partial=False):
    raw=list(csv.DictReader((HUB/"table5_seeds.csv").open(encoding="utf-8-sig")))
    refs={int(r["seed"]):r for r in raw if r["arm"]=="full"}
    result=[evidence(int(r["seed"]),r["arm"],r,refs[int(r["seed"])]) for r in raw]
    present=[r for r in result if r]
    if not partial and len(present)!=15:
        raise RuntimeError("Paired rerun still incomplete")
    write("table5_seeds.csv",present)
    if len(present)==15:
        groups=[]
        for arm in ARMS:
            rows=[r for r in present if r["arm"]==arm]
            assert sorted(r["seed"] for r in rows)==[1,2,3]
            groups.append(dict(arm=arm,A_mean=mean(r["f_A"] for r in rows),A_sd=stdev(r["f_A"] for r in rows),
                               B_mean=mean(r["f_B"] for r in rows),B_sd=stdev(r["f_B"] for r in rows),
                               time_mean=mean(r["used_s"] for r in rows),cut_mean=mean(r["cut_rounds"] for r in rows)))
        write("table5_summary.csv",groups)
    print(f"{len(present)}/15 paired records checked under {OBJECTIVE}")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--available",action="store_true")
    main(parser.parse_args().available)
