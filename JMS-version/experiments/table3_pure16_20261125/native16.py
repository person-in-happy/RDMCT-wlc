"""Frozen proposal order for both 16-wafer pure recipes."""
import sys
import subprocess
import time
from pathlib import Path
import psutil
from common16 import HERE,JMS,OUT,save,load,sha

def to_slots(doc,mode):
    names={w["identity"]:i for i,w in enumerate(sorted([w for w in load(OUT/mode/"raw/schedule.json")["jobs"] if w["product"]],key=lambda w:w["pjob_index"]))}
    groups={p["id"]:p["members"] for p in doc["pairs"]}
    first=min(r["chamber"] for r in doc["cycles"])
    coords={}
    for step in doc["cycles"]:
        if step["mode"]=="clean":raise ValueError("This proposal uses a no-clean cycle skeleton")
        c=step["chamber"]-first;q=step["index"]
        coords[f"use{c,q}"]=1
        coords[f"start{c,q}"]=round(step["start"])
        for pair in step["pairs"]:
            side=int(pair==step["front"])
            if mode=="2x2" and not side:continue
            for name in groups[pair]:
                if name in names:coords[f"w{names[name]}_{c}_{q}_{side}"]=1
    return coords

def from_batch(mode,proof):
    rows=load(proof)["minimizing_relaxed_batches"]
    values={};counters=[0,0];index=0
    for recipe,c,n,t in rows:
        q=counters[c];counters[c]+=1
        values[f"use{c,q}"]=1;values[f"start{c,q}"]=t
        for i in range(n):
            side=int(i>=max(1,n-2)) if mode=="4x1" else 1
            values[f"w{index}_{c}_{q}_{side}"]=1
            index+=1
    if mode=="2x2":
        for c in range(2):
            q=counters[c]
            if q:
                values[f"use{c,q}"]=1;values[f"start{c,q}"]=values[f"start{c,q-1}"]+94
    assert index==16
    return values

def main(mode):
    folder=OUT/mode/"native"
    folder.mkdir(parents=True,exist_ok=True)
    proof=JMS/"results/table3_grid16_20261125"/f"batch_bound_pure_{mode}.json"
    old=JMS/"results/optimality_work_20261021"/("manuscript_warm_n16_H10_4x1_transfer" if mode=="4x1" else "manuscript_warm_n16_H10_2x2_v2")/"result.json"
    proto=folder/"protocol.json"
    if not proto.exists():
        archive=folder/"archived_skeleton.json";batch=folder/"relaxed_batch_skeleton.json"
        save(archive,to_slots(load(old),mode));save(batch,from_batch(mode,proof))
        save(proto,dict(started=time.time(),seed=1,level=[.10,.01,.0001],primary_start=sha(OUT/mode/"prepared/assignment.json.gz"),
            archive_source=str(old.relative_to(JMS)),archive_sha256=sha(old),batch_proof=str(proof.relative_to(JMS)),batch_sha256=sha(proof),
            order="SPBS then native incumbents obtained from historical pair/cycle assignments, relaxed-batch assignments, and available product-projection incumbents in discovery order. A validated UB or certified external LB improvement can trigger a gate. No earlier gate is replaced.",
            native_budget_per_skeleton=[180,180,120],first_two_caps=([935,906] if mode=="4x1" else [900,863]),
            first=[dict(source=str(archive.relative_to(JMS)),sha256=sha(archive)),dict(source=str(batch.relative_to(JMS)),sha256=sha(batch))]))
    design=load(proto)
    attempts=[]
    def run(p,cap,seconds,tag):
        cmd=[sys.executable,"-B","-u","-X","utf8",str(HERE/"candidate16.py"),mode,str(p),str(cap),str(seconds),tag]
        endpoint=OUT/mode/"search"/tag/"result.json"
        for proc in psutil.process_iter(["cmdline"]):
            args=proc.info["cmdline"] or []
            if args[-6:]==cmd[-6:]:proc.wait()
        if not endpoint.exists():subprocess.run(cmd,check=True)
        attempts.append(dict(file=str(endpoint.relative_to(JMS)),sha256=sha(endpoint)))
    for i,data in enumerate(design["first"]):
        p=JMS/data["source"]
        assert sha(p)==data["sha256"]
        run(p,design["first_two_caps"][i],design["native_budget_per_skeleton"][i],f"{i+1}_{p.stem}")
    projection=OUT/mode/"projection"
    ordered=sorted(projection.glob("candidate_*.json"),key=lambda p:-int(p.stem.split("_")[1]))
    for i,p in enumerate(ordered[:3]):
        run(p,int(p.stem.split("_")[1]),120,f"p{i+1}_{p.stem}")
    save(folder/"result.json",dict(attempts=attempts,projected_candidates_available=len(ordered)))

if __name__=="__main__":main(sys.argv[1])
