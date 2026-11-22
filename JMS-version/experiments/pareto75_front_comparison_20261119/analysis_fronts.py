"""Independent scoring of returned and untruncated Pareto sets with paired inference."""
from collections import defaultdict
from itertools import groupby
from math import comb, inf, isfinite
from pathlib import Path
from statistics import median
import csv
import json
import sys

from case_setup import HERE, OUT, OLD, ROOT, CASES, METHODS, SEEDS, NFE, load_schedule, metrics, read, save, signature
from paired import jobs,spec
from trial import exported,founders
from review import hypervolume as stripe_hv

REPORT=HERE/"review"
NAMES={"domain":"领域搜索","uniform":"均匀选片","nsga2":"NSGA-II","moead":"MOEA/D","fixed":"固定结构"}
OLD_OUT=OLD/"results/formal02"
OLD_REVIEW=OLD/"review"


def csvrows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def table(path,records):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def nd(points):
    result=[]
    for a,b in sorted(set(map(tuple,points))):
        if not result or b<result[-1][1]:
            result.append((a,b))
    return result


def hv(points,bounds):
    previous,total=1.1,0.
    for a,b in nd(points):
        x=(a-bounds[0][0])/(bounds[0][1]-bounds[0][0])
        y=(b-bounds[1][0])/(bounds[1][1]-bounds[1][0])
        if x<1.1 and y<previous:
            total+=(1.1-x)*(previous-y)
            previous=y
    assert abs(total-stripe_hv(points,bounds))<1e-10
    return total


def coverage(first,second):
    return sum(any(a<=x and b<=y for a,b in first) for x,y in second)/len(second)


def b_at(points,deadline):
    return min((b for a,b in points if a<=deadline),default=inf)


def step_at_least_half(fronts):
    required=(len(fronts)+1)//2
    curve=[]
    for deadline in sorted({a for fr in fronts for a,_ in fr}):
        b=sorted(b_at(fr,deadline) for fr in fronts)[required-1]
        if isfinite(b) and (not curve or b<curve[-1][1]):
            curve.append((deadline,b))
    return curve


def exact_comparison(differences):
    values=sorted(differences)
    n=len(values)
    w=sum(d>1e-10 for d in values)
    l=sum(d<-1e-10 for d in values)
    trials=w+l
    p=min(1.,2*sum(comb(trials,i) for i in range(min(w,l)+1))/2**trials) if trials else 1.
    k=max(k for k in range(1,n//2+1) if 1-2*sum(comb(n,i) for i in range(k))/2**n>=.95)
    probability=1-2*sum(comb(n,i) for i in range(k))/2**n
    return dict(wins=w,ties=n-w-l,losses=l,median_delta=median(values),ci_lo=values[k-1],ci_hi=values[-k],
                ci_coverage=probability,p_sign=p)


def records(validate=True):
    assert read(OUT/"finished.json")=={"cells":98,"source_match":True}
    assert read(OUT/"protocol.json")==json.loads(json.dumps(spec()))
    stat={}
    fronts={}
    shared={}
    archives={}
    by_sig={}
    verified={}
    raw_entries=[]
    for case,m,s in jobs():
        folder=OUT/case/f"{m}_{s}"
        r=read(folder/"run.json")
        info=read(OUT/"shared"/(case+".json"))
        bounds=info["bounds"]
        assert r["warm"]==[info["a"],info["b"]] and (r["case"],r["method"],r["seed"])==(case,m,s)
        vals=[(x["a"],x["b"]) for x in r["archive"]]
        kept=[(x["a"],x["b"]) for x in r["archive"] if x["submitted"]]
        assert vals==nd(vals)==nd((a,b) for t,a,b in r["trace"]) and kept==exported(vals)
        if m!="fixed":
            assert r["stats"]["evaluations"]==NFE and len(r["common_population"])==12
            assert [tuple(g) for g,obj in r["common_population"]]==founders()
            shared.setdefault(case,r["common_population"])
            assert shared[case]==r["common_population"]
        for x in r["archive"]:
            sig=x["sig"]
            assert 0<=x["found_s"]<=r["elapsed_s"] and sig==Path(x["file"]).name.split(".")[0]
            by_sig.setdefault(case,{})[(x["a"],x["b"])]=dict(source="paired",case=case,method=m,seed=s,
                sig=sig,file=(folder/x["file"]).relative_to(HERE).as_posix())
            raw_entries.append(dict(case=case,method=m,seed=s,A=x["a"],B=x["b"],submitted=x["submitted"],
                                    admission_s=x["found_s"],sig=sig,file=(folder/x["file"]).relative_to(HERE).as_posix()))
            if validate:
                assert (folder/x["file"]).is_file()
                if sig not in verified:
                    data=load_schedule(folder/x["file"])
                    cert=read(OUT/"audits"/(sig+".json"))
                    dim=read(OUT/"audits"/(case+"_dimensions.json"))
                    assert signature(data)==sig and cert["sig"]==sig and cert["case"]==case and cert["physical"]
                    assert dim["scalar_vector_positive_match"] and dim["corrupt_single_lane_rejected"]
                    assert (cert["rows"],cert["variables"])==(dim["rows"],dim["variables"])
                    assert metrics(data,25)==cert["metrics"] and (x["a"],x["b"])==(cert["original_A"],cert["original_B"])
                    verified[sig]=(cert["original_A"],cert["original_B"])
                assert verified[sig]==(x["a"],x["b"])
        pair=(case,m,s)
        fronts[pair]=kept
        archives[pair]=vals
        q=dict(case=case,method=m,seed=s,evaluations=r["stats"]["evaluations"],lp_calls=r["stats"]["lp_attempts"],
               bound_skips=r["stats"].get("bound_screened",0),biased_selections=r["stats"].get("biased_selections",0),
               wall_s=r["elapsed_s"],submitted=len(kept),internal=len(vals),HV=hv(kept,bounds),
               HV_all=hv(vals,bounds),min_A=kept[0][0],min_B=kept[-1][1])
        if m!="fixed":
            for f in (12,40,80,160):
                q[f"HV_at_{f}"]=hv(exported(map(tuple,r["checkpoints"][str(f)])),bounds)
            assert abs(q["HV_at_160"]-q["HV"])<1e-12
        stat[pair]=q
    if validate:
        assert read(OUT/"audits/complete.json")["distinct"]==len(verified)
    return stat,fronts,archives,raw_entries,by_sig


def analyze(preview=False):
    stat,fronts,archives,entries,source=records(not preview)
    comparisons=[]
    summary=[]
    curve_rows=[]
    combined=[]
    for c in CASES:
        for m in (*METHODS,"fixed"):
            ss=SEEDS if m!="fixed" else (0,)
            group=[stat[c,m,s] for s in ss]
            f=[fronts[c,m,s] for s in ss]
            curve=step_at_least_half(f)
            for a,b in curve:
                curve_rows.append(dict(case=c,method=m,A_deadline=a,B_attained=b,successes=sum(b_at(fr,a)<=b for fr in f),runs=len(f)))
            q=dict(case=c,method=m,runs=len(ss),HV=median(r["HV"] for r in group),HV_all=median(r["HV_all"] for r in group),
                HV_min=min(r["HV"] for r in group),HV_max=max(r["HV"] for r in group),
                min_A=median(r["min_A"] for r in group),min_B=median(r["min_B"] for r in group),
                wall_s=median(r["wall_s"] for r in group),lp=median(r["lp_calls"] for r in group),
                bound_skips=sum(r["bound_skips"] for r in group))
            q["common_HV"]=median(r["HV_at_12"] for r in group) if m!="fixed" else None
            q["better_than_shared"]=sum(r["HV"]>r["HV_at_12"]+1e-10 for r in group) if m!="fixed" else None
            summary.append(q)
        for m in ("nsga2","moead","uniform"):
            diff=[stat[c,"domain",s]["HV"]-stat[c,m,s]["HV"] for s in SEEDS]
            other=[stat[c,"domain",s]["HV_all"]-stat[c,m,s]["HV_all"] for s in SEEDS]
            r=dict(case=c,opponent=m,**exact_comparison(diff))
            cf=[coverage(fronts[c,"domain",s],fronts[c,m,s]) for s in SEEDS]
            cr=[coverage(fronts[c,m,s],fronts[c,"domain",s]) for s in SEEDS]
            r.update(full_HV_median_delta=median(other),full_HV_wins=sum(v>1e-10 for v in other),
                     domain_covers_only=sum(x==1 and y<1 for x,y in zip(cf,cr)),
                     opponent_covers_only=sum(y==1 and x<1 for x,y in zip(cf,cr)),
                     mutually_cover=sum(x==y==1 for x,y in zip(cf,cr)),
                     incomparable=sum(x<1 and y<1 for x,y in zip(cf,cr)))
            assert sum(r[k] for k in ("domain_covers_only","opponent_covers_only","mutually_cover","incomparable"))==len(SEEDS)
            comparisons.append(r)
        all_pts={p:dict(d) for p,d in source[c].items()}
        for a,b in nd(all_pts):
            combined.append(dict(scope="paired",A=a,B=b,**all_pts[a,b]))
        if c=="mix37":
            for row in read(OLD_OUT/"pooled/front.json"):
                p=(row["a"],row["b"])
                cert=read(OLD_OUT/"row_audit"/(row["schedule_sha256"]+".json"))
                assert (cert["metrics"]["cmax"],cert["metrics"]["secondary"])==p
                all_pts.setdefault(p,dict(case=c,source="historical90s",method=row["method"],seed=row["seed"],
                    sig=row["schedule_sha256"],file=(OLD_OUT/row["file"]).relative_to(ROOT).as_posix()))
            for a,b in nd(all_pts):
                combined.append(dict(scope="both_protocols",A=a,B=b,**all_pts[a,b]))
    largest=0
    for i,r in enumerate(sorted(comparisons,key=lambda r:r["p_sign"])):
        largest=max(largest,min(1.,(len(comparisons)-i)*r["p_sign"]))
        r["p_holm"]=largest
        r["reject_holm_05"]=largest<=.05
    if preview:
        print([(r["case"],r["opponent"],r["wins"],r["ties"],r["losses"],round(r["median_delta"],6),round(r["p_holm"],5),r["incomparable"]) for r in comparisons])
        return
    REPORT.mkdir(exist_ok=True)
    # Write the absolute provenance of union points once, using repo-relative paths for both cohorts.
    for r in combined:
        if r["source"]=="paired":
            r["file"]=(HERE/r["file"]).relative_to(ROOT).as_posix()
    ordinary=[r for r in stat.values() if r["method"]!="fixed"]
    fixed=[r for r in stat.values() if r["method"]=="fixed"]
    for r in fixed:
        for f in (12,40,80,160):
            r[f"HV_at_{f}"]=None
    for filename,rr in (("runs",ordinary+fixed),("methods",summary),("contrasts",comparisons),("attainment",curve_rows),
                        ("all_witnesses",entries),("pooled_fronts",combined)):
        table(REPORT/(filename+".csv"),rr)
    verify=dict(cells=len(stat),paired_cells=len(ordinary),seeds=SEEDS,all_archive_entries=len(entries),
                submitted_entries=sum(r["submitted"] for r in stat.values()),unique_original=len({r["sig"] for r in entries}),
                case_dimensions={c:read(OUT/"audits"/(c+"_dimensions.json")) for c in CASES},
                summaries=summary,comparisons=comparisons,
                pooled={c:{scope:len([r for r in combined if r["scope"]==scope and r["case"]==c])
                           for scope in sorted({r["scope"] for r in combined if r["case"]==c})} for c in CASES})
    save(REPORT/"verified.json",verify)
    print(f"Verified {verify['cells']} cells, {verify['unique_original']} distinct witnesses",flush=True)


if __name__=="__main__":
    analyze("--preview" in sys.argv)
