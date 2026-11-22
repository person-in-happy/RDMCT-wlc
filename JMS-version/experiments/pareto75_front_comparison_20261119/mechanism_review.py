"""Review the fresh ablation cohort and index all verified 75-wafer engineering choices."""
from collections import defaultdict
from math import ceil
import json
import random
from statistics import median
import sys
from case_setup import CASES, HERE, ROOT, OUT, NFE, load_schedule, metrics, read, save, signature
from trial import exported, founders
from mechanism import MOUT,MSEEDS,ARMS,cells,contract
from analysis_fronts import nd,hv,coverage,exact_comparison,table,REPORT,csvrows
from audit_fronts import DEST,PACK,AUDIT_WORKERS,verify_pack
from paired import execute
import paired

MAUD=MOUT/"audits"
LABEL={"full":"完整领域搜索","no_blocks":"关闭局部生产块调整","random_init":"随机结构初始化"}


def status(message):
    import time
    print(message,flush=True)
    with (MOUT/"audit_progress.log").open("a",encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ")+message+"\n")


def audit():
    assert read(MOUT/"finished.json")=={"cells":72,"source_match":True}
    assert read(MOUT/"protocol.json")==json.loads(json.dumps(contract()))
    assert (DEST/"complete.json").exists()
    MAUD.mkdir(exist_ok=True)
    unique=defaultdict(dict)
    for c,m,s in cells():
        folder=MOUT/c/f"{m}_{s}"
        for r in read(folder/"run.json")["archive"]:
            unique[c].setdefault(r["sig"],(tuple(r["genes"]),str(folder/r["file"])))
    reused=0
    todo=[]
    for c,paths in unique.items():
        current=[]
        for sig,(g,path) in sorted(paths.items(),key=lambda item:(item[1][0],item[0])):
            if (DEST/(sig+".json")).is_file():
                reused+=1
            elif not (MAUD/(sig+".json")).exists():
                current.append(path)
        todo.extend((c,current[k:k+PACK]) for k in range(0,len(current),PACK))
    def done(job,rr):
        for r in rr:
            save(MAUD/(r["sig"]+".json"),r)
    paired.log=status
    total=sum(len(v) for v in unique.values())
    status(f"Full original row audit: {total} distinct schedules, {reused} exact content matches in the preceding locked campaign, {len(todo)} packs for new certificates")
    execute("ablation original rows",todo,verify_pack,done,AUDIT_WORKERS,50)
    assert all(any((d/(sig+".json")).is_file() for d in (MAUD,DEST)) for tab in unique.values() for sig in tab)
    save(MAUD/"complete.json",dict(distinct=total,reused=reused,new=total-reused))
    status(f"ABLATION ORIGINAL ROWS PASS: {total} distinct schedules")


def analyze():
    assert (MAUD/"complete.json").is_file()
    assert read(MOUT/"protocol.json")==json.loads(json.dumps(contract()))
    base=read(REPORT/"verified.json")
    rr=[]
    all_rows=[]
    effects=[]
    methods=[]
    all_points=defaultdict(dict)
    checked={}
    for c,m,s in cells():
        folder=MOUT/c/f"{m}_{s}"
        run=read(folder/"run.json")
        case=read(OUT/"shared"/(c+".json"))
        qs=run["archive"]
        full=nd((x["a"],x["b"]) for x in qs)
        chosen=[(x["a"],x["b"]) for x in qs if x["submitted"]]
        assert full==[(x["a"],x["b"]) for x in qs]==nd((a,b) for t,a,b in run["trace"])
        assert chosen==exported(full) and run["stats"]["evaluations"]==NFE
        start=run["start"]
        assert len(start)==12 and run["warm"]==[case["a"],case["b"]]
        if m=="random_init":
            init=random.Random(10000+s)
            n=sum(ceil(len(p["wafers"])/4) for p in case["config"]["pjobs"])
            structures=[tuple(init.randrange(v) for v in (6,)+(1+6*n,)*3) for _ in range(6)]
            expected=[genes+(level,) for genes in structures for level in (17,0)]
            assert [tuple(g) for g,v in start]==expected
        else:
            common=read(OUT/c/"domain_101"/"run.json")["common_population"]
            assert start==common and [tuple(g) for g,v in start]==founders()
        if m=="no_blocks":
            assert run["stats"]["projected_block_moves"]>0 and all(not any(x["genes"][1:]) for x in qs)
        for x in qs:
            sig=x["sig"]
            path=folder/x["file"]
            assert sig==path.name.split(".")[0] and 0<=x["found_s"]<=run["elapsed_s"]
            if sig not in checked:
                data=load_schedule(path)
                certificate=next(read(d/(sig+".json")) for d in (MAUD,DEST) if (d/(sig+".json")).exists())
                assert signature(data)==sig and certificate["case"]==c and certificate["physical"] and certificate["sig"]==sig
                assert certificate["metrics"]==metrics(data,25)
                dims=base["case_dimensions"][c]
                assert (certificate["variables"],certificate["rows"])==(dims["variables"],dims["rows"])
                checked[sig]=(certificate["original_A"],certificate["original_B"])
            assert checked[sig]==(x["a"],x["b"])
            source=dict(case=c,source="mechanism",method=m,seed=s,sig=sig,file=path.relative_to(ROOT).as_posix())
            all_points[c].setdefault((x["a"],x["b"]),source)
            all_rows.append(dict(A=x["a"],B=x["b"],submitted=x["submitted"],**source))
        rr.append(dict(case=c,method=m,seed=s,evaluations=NFE,lp=run["stats"]["lp_attempts"],wall_s=run["elapsed_s"],
                       accepted_founders=sum(v is not None for g,v in start),HV=hv(chosen,case["bounds"]),
                       HV_founders=hv(exported(map(tuple,run["checkpoints"]["12"])),case["bounds"]),
                       HV_all=hv(full,case["bounds"]),min_A=full[0][0],min_B=full[-1][1],
                       projected=run["stats"].get("projected_block_moves",0),bound_skips=run["stats"].get("bound_screened",0)))
    assert len(checked)==read(MAUD/"complete.json")["distinct"]
    by_id={(r["case"],r["method"],r["seed"]):r for r in rr}
    for c in CASES:
        for m in ARMS:
            rs=[by_id[c,m,s] for s in MSEEDS]
            methods.append(dict(case=c,method=m,HV=median(r["HV"] for r in rs),HV_founders=median(r["HV_founders"] for r in rs),
                HV_all=median(r["HV_all"] for r in rs),min_A=median(r["min_A"] for r in rs),min_B=median(r["min_B"] for r in rs),
                seconds=median(r["wall_s"] for r in rs),lp=median(r["lp"] for r in rs)))
        for m in ("no_blocks","random_init"):
            diff=[by_id[c,"full",s]["HV"]-by_id[c,m,s]["HV"] for s in MSEEDS]
            unc=[by_id[c,"full",s]["HV_all"]-by_id[c,m,s]["HV_all"] for s in MSEEDS]
            effects.append(dict(case=c,opponent=m,**exact_comparison(diff),full_HV_median_delta=median(unc),
                                full_HV_wins=sum(v>1e-10 for v in unc)))
    high=0
    for i,v in enumerate(sorted(effects,key=lambda x:x["p_sign"])):
        high=max(high,min(1,(len(effects)-i)*v["p_sign"]))
        v.update(p_holm=high,reject_holm_05=high<=.05)
    selected={}
    for c in CASES:
        selected[c]={p:dict(r) for p,r in all_points[c].items()}
    for row in csvrows(REPORT/"pooled_fronts.csv"):
        c=row["case"]
        if (c=="mix37" and row["scope"]=="both_protocols") or (c=="mix50" and row["scope"]=="paired"):
            source={k:row[k] for k in ("case","source","method","seed","sig","file")}
            selected[c].setdefault((float(row["A"]),float(row["B"])),source)
    engineering=[]
    for c in CASES:
        for a,b in nd(selected[c]):
            src=selected[c][a,b]
            d=load_schedule(ROOT/src["file"])
            measured=metrics(d,25)
            assert signature(d)==src["sig"] and (measured["cmax"],measured["secondary"])==(a,b)
            engineering.append(dict(A=a,B=b,L_sum=measured["wait_sum"],L_max=measured["wait_max"],R=measured["rhythm"],**src))
    for filename,data in (("ablation_runs",rr),("ablation_effects",effects),("ablation_methods",methods),
                          ("ablation_witnesses",all_rows),("engineering_fronts",engineering)):
        table(REPORT/(filename+".csv"),data)
    out=dict(base_cells=base["cells"],ablation_cells=len(rr),base_unique=base["unique_original"],
             **read(MAUD/"complete.json"),combined_unique=base["unique_original"]+read(MAUD/"complete.json")["new"],
             submitted=sum(r["submitted"] for r in all_rows),entries=len(all_rows),methods=methods,effects=effects,
             combined_points={c:sum(r["case"]==c for r in engineering) for c in CASES})
    save(REPORT/"mechanism_verified.json",out)
    print("Mechanism audit",out["ablation_cells"],"runs, unique",out["distinct"],"combined Pareto",out["combined_points"],flush=True)
    for e in effects:
        print(e["case"],e["opponent"],e["wins"],e["ties"],e["losses"],round(e["median_delta"],6),round(e["p_holm"],6),flush=True)


if __name__=="__main__":
    audit()
    analyze()
