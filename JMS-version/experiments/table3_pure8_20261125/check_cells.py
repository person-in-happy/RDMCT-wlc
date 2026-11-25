"""Replay independent product residence, both gap certificates and all 18 pure-recipe rows."""
import csv
import sys
from collections import defaultdict
from run import HERE,JMS,OUT,LEVELS,atomic,load,sha
from pathlib import Path
sys.path.insert(0,str(HERE.parent/"manuscript_projection_20261120"))
import cell
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config,Integrated
from validate import validate

def objective(s):
    cfg=s["config"]
    processing=defaultdict(int)
    unused=0
    for ch in cfg["chambers"]:
        counter=0
        for c in sorted((c for c in s["cycles"] if c["chamber"]==ch),key=lambda c:c["index"]):
            if c["mode"]=="clean":
                unused+=cfg["cleaning_interval"]-counter
                counter=0
            else:
                counter+=1
                for p in c["pairs"]:
                    processing[p]+=cfg["full_time"] if c["mode"]=="4x1" else cfg["mix_time"]
            assert 0<=counter<=cfg["cleaning_interval"]
    products=[w for w in s["jobs"] if w["product"]]
    assert len(products)==8
    rs=[max(0,w["unload_start"]-w["load_end"]-processing[w["pair"]]) for w in products]
    mean=sum(rs)/8
    spread=max(rs)-min(rs)
    total=mean+(spread**2/2 if spread<=1 else (spread-.5))+unused
    return max(w["loan_end"] for w in products),mean,spread,unused,total

def main():
    allrows=[]
    checked={}
    for mode in ("4x1","2x2"):
        root=OUT/"certified"/mode
        with (root/"threshold_cells.csv").open(encoding="utf8",newline="") as f:rows=list(csv.DictReader(f))
        assert {(r["gA"],r["gB"]) for r in rows}=={(a,b) for a in LEVELS for b in LEVELS}
        initial=load(OUT/mode/"prepared/schedule.json")
        cfg=initial["config"]
        assert cfg["horizon"]==100000 and cfg["cleaning_interval"]==10 and cfg["dummy_count"]==8
        assert cfg["module_residency"]==cfg["robot_residency"]==100
        assert len(cfg["pjobs"])==1 and cfg["pjobs"][0]["mode"]==mode
        assert all(v[mode]==2 and sum(v.values())==2 for v in cfg["load_ports"].values())
        native=Integrated(Config(**cfg))
        native.model.setRealParam("numerics/feastol",1e-8)
        checked_paths=set()
        original_rows=native.model.getNConss()
        for r in rows:
            a=load(JMS/r["A_proof"]);b=load(JMS/r["B_proof"])
            assert sha(JMS/r["schedule"])==r["schedule_sha256"]==b["files"]["schedule.json"]
            assert sha((JMS/r["B_proof"]).parent/"assignment.json.gz")==b["files"]["assignment.json.gz"]
            s=load(JMS/r["schedule"])
            assert s["config"]==cfg
            primary=load((JMS/r["A_proof"]).parent/"schedule.json")
            assert primary["config"]==cfg and a["replay"]["valid"] and b["replay"]["valid"]
            assert original_rows==a["rows"]==b["original_rows"]==b["replayed_rows"]
            for folder, archived in [((JMS/r["A_proof"]).parent,primary),((JMS/r["B_proof"]).parent,s)]:
                if folder in checked_paths:
                    continue
                vals=cell.values(folder/"assignment.json.gz")
                sol=cell.attach(native,vals)
                decoded=native.result(solution=sol)
                assert validate(decoded)["valid"] and validate(archived)["valid"]
                assert all(abs(x-y)<1e-6 for x,y in zip(objective(decoded),objective(archived)))
                native.model.freeSol(sol)
                checked_paths.add(folder)
            assert sha(JMS/a["lower_source"])==a["lower_sha256"]
            assert load(JMS/a["lower_source"])["lower"]==a["lower"]
            assert b["parents"][0]["assignment_sha256"]==a["assignment_sha256"]
            c,mean,d,e,f=objective(s)
            for val,k in ((c,"f_A"),(mean,"mean"),(d,"spread"),(e,"E"),(f,"f_B")):
                assert abs(val-float(r[k]))<1e-6,(r,k,val)
            assert abs(c-a["upper"])<2e-5 and abs(objective(primary)[0]-a["upper"])<1e-6
            for prefix,gap in (("A",LEVELS[r["gA"]]),("B",LEVELS[r["gB"]])):
                u,l=float(r[prefix+"_upper"]),float(r[prefix+"_lower"])
                calculated=max(0,(u-l)/l)
                assert 0<=calculated<=gap+1e-8 and abs(calculated-float(r[prefix+"_gap"]))<1e-8
            assert abs(f-float(r["B_upper"]))<1e-5
        allrows+=rows
        native.model.freeProb()
        checked[mode]=dict(rows=9,objective_and_native_source_hashes=True,grid_sha256=sha(root/"threshold_cells.csv"),
            native_assignments_checked=len(checked_paths),native_feastol=1e-8,native_rows=original_rows,
            primary_thresholds={a:load(root/a/"A/primary.json")["upper"] for a in LEVELS})
    out=OUT/"threshold_cells.csv"
    with out.open("w",newline="",encoding="utf8") as stream:
        w=csv.DictWriter(stream,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
    atomic(OUT/"validation.json",dict(rows=18,checked=checked,combined_sha256=sha(out),code_sha256=sha(Path(__file__))))
    print("Replay and A/B bounds verified for 18 pure-recipe cells.")

if __name__=="__main__":main()
