"""Independently check 16-product native assignments, events, scores, hashes, and gate provenance."""
import csv
import os
from collections import defaultdict
from pathlib import Path
from common16 import HERE,JMS,OUT,LEVELS,setup,load,save,sha,config

def measure(doc):
    cfg=doc["config"]
    exposure=defaultdict(float)
    unused=0
    for chamber in cfg["chambers"]:
        count=0
        for row in sorted((r for r in doc["cycles"] if r["chamber"]==chamber),key=lambda r:r["index"]):
            if row["mode"]=="clean":
                unused+=cfg["cleaning_interval"]-count
                count=0
            else:
                count+=1
                for pair in row["pairs"]:exposure[pair]+=cfg["full_time"] if row["mode"]=="4x1" else cfg["mix_time"]
            assert 0<=count<=cfg["cleaning_interval"]
    jobs=[w for w in doc["jobs"] if w["product"]]
    assert len(jobs)==16 and len({w["pjob"] for w in jobs})==1
    residence=[max(0,w["unload_start"]-w["load_end"]-exposure[w["pair"]]) for w in jobs]
    avg=sum(residence)/len(residence)
    spread=max(residence)-min(residence)
    huber=spread*spread/2 if spread<=1 else spread-.5
    return dict(f_A=max(w["loan_end"] for w in jobs),mean=avg,spread=spread,E=unused,huber=huber,f_B=avg+huber+unused)

def main():
    cell=setup()
    from model import Integrated
    from validate import validate
    by_mode={};rows=[]
    for mode in ("4x1","2x2"):
        root=OUT/mode;source=root/"threshold_cells.csv"
        if not source.exists():continue
        with source.open(encoding="utf8",newline="") as stream:entries=list(csv.DictReader(stream))
        assert len({(row["gA"],row["gB"]) for row in entries})==len(entries)
        if not entries:continue
        cfg=config(mode);native=Integrated(cfg)
        native.model.setRealParam("numerics/feastol",1e-8)
        seen={}
        original=native.model.getNConss()
        def replay(path):
            d=load(path/"schedule.json")
            assert d["config"]==load(root/"prepared/schedule.json")["config"]
            pair=sha(path/"assignment.json.gz"),sha(path/"schedule.json")
            if pair not in seen:
                sol=cell.attach(native,cell.values(path/"assignment.json.gz"))
                fresh=native.result(solution=sol)
                native.model.freeSol(sol)
                assert validate(fresh)["valid"] and validate(d)["valid"]
                metrics=measure(d);measured=measure(fresh)
                assert all(abs(metrics[k]-measured[k])<2e-5 for k in metrics)
                seen[pair]=metrics
            return seen[pair]
        for row in entries:
            a,b=row["gA"],row["gB"]
            ap=JMS/row["A_proof"];bp=JMS/row["B_proof"];ar=load(ap);br=load(bp)
            assert ar["rows"]==br["original_rows"]==br["replayed_rows"]==original
            primary=replay(ap.parent);secondary=replay(bp.parent)
            assert ar["source_sha256"]==sha(JMS/ar["source"]) and ar["lower_sha256"]==sha(JMS/ar["lower_source"])
            proof=load(JMS/ar["lower_source"])
            assert proof.get("lower",proof.get("global_lower"))==ar["lower"]
            if "proof" in proof:
                core=JMS/proof["proof"]
                assert sha(core)==proof["sha256"]
                certificate=load(core)
                assert certificate["lower"]==ar["lower"]
                if "source_log" in certificate:
                    transcript=JMS/certificate["source_log"]
                    assert sha(transcript)==certificate["source_log_sha256"]
                    summary=transcript.read_text(encoding="utf8").rsplit("CpSolverResponse summary:",1)[-1]
                    assert f"best_bound: {ar['lower']:g}\n" in summary and "status: OPTIMAL" in summary
            assert ar["assignment_sha256"]==br["parents"][0]["assignment_sha256"]==sha(ap.parent/"assignment.json.gz")
            assert ar["schedule_sha256"]==br["parents"][0]["schedule_sha256"]==sha(ap.parent/"schedule.json")
            assert sha(JMS/row["schedule"])==br["files"]["schedule.json"]==row["schedule_sha256"]
            assert sha(bp.parent/"assignment.json.gz")==br["files"]["assignment.json.gz"]
            assert abs(primary["f_A"]-ar["upper"])<1e-6 and secondary["f_A"]<=ar["upper"]+2e-5
            assert abs(secondary["f_B"]-br["record"]["upper"])<2e-5
            for prefix,g in (("A",a),("B",b)):
                ub,lb=map(float,(row[prefix+"_upper"],row[prefix+"_lower"]))
                assert abs(max(0,(ub-lb)/lb)-float(row[prefix+"_gap"]))<1e-8
                assert float(row[prefix+"_gap"])<=LEVELS[g]+1e-8
            for key in ["f_A","f_B","mean","spread","E"]:assert abs(float(row[key])-secondary[key])<1e-6
            row["huber"]=secondary["huber"]
            row["source"]=bp.parent.relative_to(JMS).as_posix()
            row["parent"]=ap.parent.relative_to(JMS).as_posix()
            rows.append(row)
        by_mode[mode]=dict(rows=len(entries),native_rows=original,distinct_assignments=len(seen),input_csv_sha256=sha(source))
        native.model.freeProb()
    if rows:
        dest=OUT/"threshold_cells.csv"
        tmp=dest.with_suffix(".tmp")
        with tmp.open("w",encoding="utf8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        os.replace(tmp,dest)
        save(OUT/"validation.json",dict(rows=len(rows),expected=18,by_mode=by_mode,
            native_feastol=1e-8,combined_sha256=sha(dest),verifier=sha(Path(__file__))))
    print(by_mode,flush=True)

if __name__=="__main__":main()
