"""Recompute both table objectives from wafer events and audit every switched structure."""
from collections import defaultdict, Counter
from itertools import product
import math
from statistics import mean
from grid import JMS,R,OUT,MOD,read,digest,rel,csv_write,rows,atom


def replay(schedule):
    data=read(schedule)
    cfg=data["config"]
    exposure=defaultdict(float);unused=0
    for chamber in cfg["chambers"]:
        since=0
        for cy in sorted((v for v in data["cycles"] if v["chamber"]==chamber),key=lambda q:q["index"]):
            if cy["mode"]=="clean":
                unused+=cfg["cleaning_interval"]-since
                assert 0<since<=cfg["cleaning_interval"]
                since=0
                continue
            since+=1
            for p in cy["pairs"]:exposure[p]+=cy["end"]-cy["start"]
    mode_of={j["id"]:j["mode"] for j in cfg["pjobs"]}
    rr=defaultdict(list);all_res=[];last=0
    for w in data["jobs"]:
        if w["product"]:
            r=w["unload_start"]-w["load_end"]-exposure[w["pair"]]
            assert r>=-1.1e-5
            all_res.append(r);rr[mode_of[w["pjob"]]].append(r)
            last=max(last,w["loan_end"])
    spread=max(max(values)-min(values) for values in rr.values())
    avg=mean(all_res);return dict(f_A=last,mean=avg,spread=spread,clean_deficit=unused,square=spread**2/2,f_B=avg+spread**2/2+unused)


def close(x,y,eps=1e-4):return abs(float(x)-float(y))<=eps


def run():
    grid=rows(OUT/"threshold_cells.csv")
    structure=rows(OUT/"structure_cells.csv")
    assert (len(grid),len(structure))==(108,9)
    old={(r["case"],r["gA"],r["gB"]):r for r in rows(R/"table3_grid16_20261125/threshold_cells.csv")}
    levels={"10pct":.1,"1pct":.01,"0p01pct":.0001}
    cases=list(dict.fromkeys(r["case"] for r in grid))
    pred={}
    for r in grid:
        k=(r["case"],r["gA"],r["gB"]);assert k in old and k not in pred
        pred[k]=r;prior=old[k];cell=read(JMS/r["cell"]);settings=cell["config"]
        path=JMS/r["schedule_path"];assert digest(path)==r["schedule_sha256"]==cell["schedule_sha256"]
        assert digest(JMS/settings["A"])==prior["primary_schedule_sha256"]==r["primary_schedule_sha256"]
        assert digest(JMS/settings["values"])==settings["assignment_sha256"]
        old_native=read(JMS/cell["proof"]);assert digest(JMS/cell["proof"])==cell["certificate_sha256"]
        assert old_native["replay"]["valid"] and old_native["original_rows"]==old_native["replayed_rows"]>0
        assert old_native["parents"][0]["schedule_sha256"]==r["primary_schedule_sha256"]
        assert old_native["parents"][0]["assignment_sha256"]==settings["assignment_sha256"]
        checks=replay(path)
        assert all(close(checks[v],r[v]) for v in checks),(k,checks,r)
        for prefix,threshold in (("A",r["gA"]),("B",r["gB"])):
            ub,lb,gap=[float(r[f"{prefix}_{i}"]) for i in ("upper","lower","gap")]
            assert lb<=ub+2e-5 and ub-lb<=abs(lb)*levels[threshold]+2e-5
            assert gap<=levels[threshold]+1e-7
        assert close(r["A_upper"],checks["f_A"]) and close(r["B_upper"],checks["f_B"])
        assert close(r["A_lower"],prior["A_lower"]) and close(r["A_upper"],prior["A_upper"])
        if r["method"].startswith("Huber"):
            assert close(cell["B_lower"],old_native["record"]["lower"])
    assert set(pred)==set(product(cases,levels,levels))
    for a,c in product(levels,cases):
        assert len({pred[c,a,b]["primary_schedule_sha256"] for b in levels})==1
    h6=[]
    for r in structure:
        cell=read(JMS/r["cell"]);c=cell["config"]
        assert c["budget"]==30 and int(r["seed"])==c["seed"]
        stats=replay(JMS/r["schedule"]);start=replay(JMS/c["A"]);proof=read(JMS/cell["proof"])
        assert proof["replay"]["valid"] and proof["original_rows"]==proof["replayed_rows"]
        assert all(close(stats[k],r[k]) for k in ("f_A","f_B","mean","spread","square")) and close(r["initial_f_B"],start["f_B"])
        assert proof["mode"]=="fixed" and proof["record"]["seconds"]<=30.5
        h6.append(dict(name=r["name"],seed=r["seed"],B_status=proof["record"]["status"],B_seconds=proof["record"]["seconds"],B_gap=r["B_gap"]))
    ranking=[]
    for a,b in product(levels,levels):
        item=dict(gA=a,gB=b)
        for metric in ("f_A","f_B"):
            item[metric]=round(mean(float(pred[c,a,b][metric])/max(1.,min(float(pred[c,i,j][metric]) for i,j in product(levels,levels))) for c in cases),6)
        ranking.append(item)
    counts=Counter(r["method"] for r in grid)
    choice=min(ranking,key=lambda row:(row["f_A"],row["f_B"],-levels[row["gA"]],-levels[row["gB"]]))
    raises=[c for c in cases if any(float(pred[c,a,b]["f_A"])-float(pred[c,a2,b]["f_A"])>2e-4 and
            float(pred[c,a2,b]["f_B"])-float(pred[c,a,b]["f_B"])>2e-4 for a,a2 in zip(levels,list(levels)[1:]) for b in levels)]
    csv_write(OUT/"normalized_means.csv",ranking)
    atom(OUT/"validation.json",dict(table3=108,approaches=counts,sixteen_H6_checked=h6,selected=choice,tradeoffs=raises,
        grid_sha256=digest(OUT/"threshold_cells.csv"),structure_sha256=digest(OUT/"structure_cells.csv"),
        solver_sha256=digest(MOD/"solver.py"),score_sha256=digest(MOD/"score.py"),
        gantt_manifest_sha256=digest(JMS/"figures/square_gantt_20261125/manifest.json")))
    print(choice,raises,counts,flush=True)

if __name__=="__main__":run()
