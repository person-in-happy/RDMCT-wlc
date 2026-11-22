"""Product-only reruns. All source schedules, solver settings and budgets are archived by cell."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import math
import os
import subprocess
import sys
import time

from objective import HERE, JMS, ROOT, objective_terms, product_metrics
sys.path.insert(0, str(HERE.parent/"manuscript_projection_20261120"))
import cell
from protocol import read, save, sha
from design import LEVELS, TUNING, sparse

R=JMS/"results"
OUT=R/"product_wait_20261122"
PRIMARY=R/"manuscript_certified_gaps_20261119_r3"
COMP=R/"component_gap_restore_20261119_r1"
MATCH=R/"matched_controls_20261122_r2"
PROJ=R/"manuscript_projection_20261120_r1"
PYTHON=sys.executable


def protocol():
    jobs={}
    catalog={c["id"]:c for c in read(R/"manuscript_cases_A0p001pct_B0p001pct_20261119/campaign.json")["cases"]}
    def job(key,case,seed,kind,source,seconds=None,gap=None,rho=None,weight=25,schedule="schedule.json",
            assignment="assignment.json.gz",eligible=True):
        schedule,assignment=source/schedule,source/assignment
        digest=sha(schedule),sha(assignment)
        for archive in ("evidence.json","stage.json"):
            if (source/archive).exists():
                evidence=read(source/archive)
                if "schedule_sha256" in evidence and schedule.name=="schedule.json":
                    assert digest==(evidence["schedule_sha256"],evidence["assignment_sha256"]),key
        jobs[key]=dict(case=case,seed=seed,kind=kind,seconds=seconds,gap=gap,rho=rho,weight=weight,
            schedule=schedule.relative_to(ROOT).as_posix(),assignment=assignment.relative_to(ROOT).as_posix(),
            schedule_sha256=digest[0],assignment_sha256=digest[1],parent_eligible=eligible,
            backend=catalog[case]["backend"],n=catalog[case]["n"])
    for case,seed,arm in read(MATCH/"design.json")["jobs"]:
        folder=MATCH/f"{case}__s{seed}__{arm}"
        prior=read(folder/"result.json")
        key="matched__"+folder.name
        if arm=="B":
            src=catalog[case]
            job(key,case,seed,"B",ROOT,300,schedule=src["source"],assignment=src["assignment"])
            assert jobs[key]["assignment_sha256"]==prior["input_sha256"]
        elif arm=="A":
            job(key,case,seed,"score",folder/"free",eligible=prior["eligible"])
        else:
            stages=prior["stages"][:-1]
            valid=all(s["record"]["seconds"]<=s["budget"]+1 and s["record"]["status"].lower() not in
                      ("memlimit","memorylimit","userinterrupt","unknown") for s in stages)
            job(key,case,seed,"fixed",folder/("free" if arm=="AB" else "primary"),30,eligible=valid)
    for case in TUNING:
        for a in LEVELS:
            for b in LEVELS:
                job(f"grid__{case}__{a}__{b}",case,1,"fixed",PRIMARY/"runs"/case/"full"/("A_"+a),gap=LEVELS[b])
        for arm in ("no_spbs","no_rerank","feature_only","hem_spbs","greedy"):
            source=(PRIMARY if arm in ("no_spbs","no_rerank") else COMP)/"runs"/case/arm/"A_0p01pct"
            for b in LEVELS:
                job(f"component__{case}__{arm}__{b}",case,1,"fixed",source,gap=LEVELS[b])
        for b in LEVELS:
            source=PROJ/"runs"/f"{case}__selected_no_spbs"/"A"
            if source.exists():
                job(f"cp__{case}__{b}",case,1,"fixed",source,gap=LEVELS[b])
    for case in ("D_n4_mixed_H10","D_n16_4x1","E_n16_2x2"):
        for seed in (1,2,3):
            p=PROJ/"runs"/f"{case}__budget_A_s{seed}"
            valid=read(p/"evidence.json")["budget_eligible"]
            job(f"projected__{case}__s{seed}",case,seed,"fixed",p,30,eligible=valid)
            for rho in (.01,.1,1):
                src=catalog[case]
                job(f"joint__{case}__s{seed}__{rho:g}",case,seed,"joint",ROOT,300,rho=rho,
                    schedule=src["source"],assignment=src["assignment"])
            if case=="E_n16_2x2":
                for w in (0,5,25,100):
                    job(f"rhythm__{case}__s{seed}__{w}",case,seed,"fixed",p,60,weight=w,eligible=valid)
    for c in catalog.values():
        if "tab:refinement-ablation-cn" not in c["manuscript"]: continue
        base=(ROOT/c["source"]).parent
        for seed in (1,2,3):
            source=base.parent.parent/"runs"/f"{base.name}__s{seed}__refined"
            job(f"refine__{c['id']}__s{seed}",c["id"],seed,"fixed",source,30,
                schedule="phase1.json",assignment="variables_phase1.json")
            other=PROJ/"runs"/f"{c['id']}__budget_A_s{seed}"
            if other.exists():
                job(f"projected__{c['id']}__s{seed}",c["id"],seed,"fixed",other,30,
                    eligible=read(other/"evidence.json")["budget_eligible"])
    return jobs


def worker(key):
    t=read(OUT/"protocol.json")["jobs"][key]
    folder=OUT/"runs"/key
    folder.mkdir(parents=True,exist_ok=True)
    src,assign=ROOT/t["schedule"],ROOT/t["assignment"]
    if (sha(src),sha(assign))!=(t["schedule_sha256"],t["assignment_sha256"]): raise ValueError("Changed input")
    data,vs=read(src),cell.values(assign)
    start=product_metrics(data)
    sys.path.insert(0,str(cell.BACKENDS[t["backend"]]))
    import model
    from validate import validate
    cfg=model.Config(**data["config"])
    x=model.Integrated(cfg)
    m=x.model
    cell.scip_settings(m,t,folder)
    native=cell.attach(x,vs)
    rebuilt=x.result(solution=native)
    parent_check=validate(data)
    if not parent_check["valid"] or any(abs(product_metrics(rebuilt)[k]-start[k])>cell.EPS for k in start):
        raise ValueError("Archived schedule disagrees with the assignment or failed replay")
    m.freeSol(native)
    record=dict(status="replayed",seconds=0,lower=None,upper=None,gap=None)
    output=data
    if t["kind"]!="score":
        variables=m.getVars(transformed=False)
        fixed=t["kind"]=="fixed"
        if fixed:
            for v in variables:
                if v.vtype()!="CONTINUOUS" and not v.name.startswith("sync_"):
                    bit=round(vs.get(v.name,0))
                    m.chgVarLb(v,bit)
                    m.chgVarUb(v,bit)
            m.addCons(x.cmax<=start["cmax"]+1e-6)
        # Correct inactive big-M epigraph warm values in the original model.
        for c in cfg.chambers:
            for q in range(2,x.Q):
                active=all(vs.get(x.keep[c,i].name,0)>.5 for i in (q,q-1))
                times=[vs.get(x.cy.start[c,i].name,0.) for i in (q,q-1,q-2)]
                vs[f"rhythm_{c}_{q}"]=max(0.,abs(times[0]-2*times[1]+times[2])-(0 if active else x.M))
        score,maximum,extra=objective_terms(x,vs,fixed,t["weight"])
        def measured(a):
            value=a["wait_sum"]+10*a["wait_max"]+t["weight"]*a["rhythm"]
            if t["kind"]=="joint":
                return a["cmax"]/max(1.,start["cmax"])+t["rho"]*value/max(1.,start["secondary"])
            return value
        objective=(x.cmax/max(1.,start["cmax"])+t["rho"]*score/max(1.,start["secondary"])
                   if t["kind"]=="joint" else score)
        m.setObjective(objective,"minimize")
        warm=cell.attach(x,vs|extra|{maximum.name:start["wait_max"],x.cmax.name:start["cmax"]})
        if abs(m.getSolObjVal(warm)-measured(start))>cell.EPS: raise ValueError("Warm objective differs")
        m.addSol(warm)
        m.optimize()
        s=m.getBestSol()
        if s is None: raise ValueError("No incumbent despite checked warm assignment")
        sol={v.name:m.getSolVal(s,v) for v in m.getVars(transformed=False)}
        lower,upper=float(m.getDualbound()),float(m.getPrimalbound())
        gap=0. if abs(upper-lower)<1e-8 else (abs(upper-lower)/min(abs(upper),abs(lower)) if lower*upper>0 else None)
        record=dict(status=str(m.getStatus()),seconds=m.getSolvingTime(),upper=upper,lower=lower,gap=gap,nodes=m.getNNodes())
        m.freeTransform()
        out=cell.attach(x,sol)
        output=x.result(solution=out)
        metrics=product_metrics(output)
        if abs(measured(metrics)-upper)>cell.EPS or (fixed and metrics["cmax"]>start["cmax"]+cell.EPS):
            raise ValueError("Final scheduled events disagree with solver")
        if t["gap"] is not None and not (record["status"] in ("optimal","gaplimit") and gap is not None and gap<=t["gap"]+1e-9):
            raise ValueError(f"Missed threshold {record}")
        save(folder/"assignment.json.gz",sparse(sol))
        save(folder/"schedule.json",output)
    replay=validate(output)
    if not replay["valid"]: raise ValueError(replay["errors"][:5])
    valid=t["parent_eligible"] and record["status"] not in ("memlimit","memorylimit","unknown","userinterrupt") and (
        t["seconds"] is None or record["seconds"]<=t["seconds"]+1)
    files={name:sha(folder/name) for name in ("schedule.json","assignment.json.gz") if (folder/name).exists()}
    save(folder/"result.json",dict(job=t,objective_scope="product_routes_and_active_pitch",initial=start,
         measured=product_metrics(output),record=record,original_rows=m.getNConss(),replay=replay,eligible=valid,files=files))


def campaign():
    import psutil
    jobs=protocol()
    save(OUT/"protocol.json",dict(jobs=jobs,solver_threads=1,concurrency_limit=6,large_free_limit=1,
         objective="sum(product waits) + 10*max(product waits) + weight*active physical pitch",
         primary_reuse="Published product-return objective and certified handoff",source_hashes={p.name:sha(p) for p in HERE.glob("*.py")}))
    pending=[k for k in jobs if not (OUT/"runs"/k/"result.json").exists()]
    done=len(jobs)-len(pending)
    def priority(key):
        t=jobs[key]
        if t["kind"] in ("B","joint"): return (0 if t["kind"]=="B" else 2,t["n"],key)
        if key.startswith("grid__"): return (1,0,key)
        return (3,t["n"],key)
    pending.sort(key=priority)
    active={}; failed=[]
    started=time.monotonic()
    def launch(k):
        folder=OUT/"runs"/k
        folder.mkdir(parents=True,exist_ok=True)
        with (folder/"worker.log").open("w",encoding="utf8") as f:
            return subprocess.run([PYTHON,"-B","-X","utf8","-u",__file__,"--cell",k],stdout=f,stderr=subprocess.STDOUT).returncode
    with ThreadPoolExecutor(6) as pool:
        while pending or active:
            for k,ft in list(active.items()):
                if ft.done():
                    if ft.result(): failed.append(k)
                    else: done+=1
                    del active[k]
            for k in pending.copy():
                if len(active)>=6: break
                big=lambda key: jobs[key]["n"]>=16 and jobs[key]["kind"]=="joint"
                if big(k) and any(big(i) for i in active): continue
                # Memory reservation for simultaneous SCIP construction/presolve.
                need=(6 if big(k) else 2.4 if jobs[k]["n"]>=8 else 1.)*1024**3
                if psutil.virtual_memory().available<need+3*1024**3: continue
                active[k]=pool.submit(launch,k);pending.remove(k)
                time.sleep(.2)
            eta=(sum(jobs[k]["seconds"] or 2 for k in pending)+sum(jobs[k]["seconds"] or 2 for k in active))/max(1,len(active))
            print(f"{done}/{len(jobs)} completed, {len(failed)} failed, {len(active)} active, ETA ~{eta/60:.1f} min",flush=True)
            save(OUT/"progress.json",dict(completed=done,total=len(jobs),failed=failed,active=list(active),pending=len(pending)))
            if active or pending: time.sleep(2)
    return int(bool(failed))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cell")
    args=parser.parse_args()
    if args.cell: worker(args.cell)
    else: sys.exit(campaign())
