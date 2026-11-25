"""Optimize the Huber residence objective over the original model with a convex quadratic epigraph."""
import argparse
from pathlib import Path
import sys
import time

from score import DELTA_SECONDS, metrics, physical_lower

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "manuscript_projection_20261120"))
import cell
from protocol import read, save, sha


def objective_terms(x, values, fixed, range_weight=1.0, clean_weight=1.0):
    """Add residence and range rows. Return the linear objective and checked-start auxiliaries."""
    from scip_imports import scip

    if min(range_weight, clean_weight) < 0:
        raise ValueError("Expected nonnegative weights")
    model, cfg = x.model, x.cfg
    durations = {"4x1": cfg.full_time, "2x2": 2 * cfg.mix_time}
    groups = {mode: [g for g in x.groups if g.mode == mode] for mode in sorted({g.mode for g in x.groups})}
    cap = float(cfg.horizon)
    if getattr(cfg, "chamber_residency_basis", None) == "nonprocessing":
        cap = min(cap, cfg.module_residency)
    initial = {}
    range_var = model.addVar(name="residence_spread", lb=0, ub=cap)
    bounds = {}
    actual = {mode: [] for mode in groups}
    for mode in groups:
        bounds[mode] = tuple(model.addVar(name=f"residence_{end}_{mode}", lb=0, ub=cap)
                             for end in ("min", "max"))
        low, high = bounds[mode]
        model.addCons(range_var >= high - low)
    terms = []
    for j in x.jobs.values():
        if j["product"] is None:
            continue
        p, r = j["product"]
        members = {mode: [x.pair.member[g.identifier,p,r] for g in gs] for mode, gs in groups.items()}
        selected = next((mode for mode, vs in members.items() if any(values.get(v.name, 0) > .5 for v in vs)), None)
        if fixed and selected is None:
            continue
        flags = {mode: scip.quicksum(vs) for mode, vs in members.items()}
        processing = durations[selected] if fixed else scip.quicksum(durations[k]*v for k,v in flags.items())
        residence = j["unload_s"] - j["load_e"] - processing
        terms.append(residence)
        if selected:
            offset = values.get(j["unload_s"].name, 0.) - values.get(j["load_s"].name, 0.) - cfg.handling
            actual[selected].append(max(0., offset - durations[selected]))
        for mode in ([selected] if fixed else groups):
            relax = 0 if fixed else cap * (1-flags[mode])
            low, high = bounds[mode]
            model.addCons(low <= residence + relax)
            model.addCons(high >= residence - relax)
        if not fixed:
            model.addCons(residence >= (2*cfg.rotation+2*cfg.handling)*flags.get("2x2",0))
    for mode, (low, high) in bounds.items():
        initial[low.name],initial[high.name] = min(actual[mode]),max(actual[mode])
    initial[range_var.name] = max(max(row)-min(row) for row in actual.values())
    deficits = []
    for chamber in cfg.chambers:
        for q in range(1, x.Q):
            clean = x.cy.kind[chamber,q,"clean"]
            if isinstance(clean, (int,float)):
                continue
            flag = values.get(clean.name,0) > .5
            previous = x.cy.counter[chamber,q-1]
            before = round(values.get(previous.name,0))
            if fixed:
                if flag:
                    deficits.append(cfg.cleaning_interval-before)
            else:
                e = model.addVar(name=f"residence_clean_deficit_{chamber}_{q}",lb=0,ub=cfg.cleaning_interval)
                model.addCons(e >= cfg.cleaning_interval*clean-previous)
                model.addCons(e <= cfg.cleaning_interval*clean)
                model.addCons(e <= cfg.cleaning_interval-previous+cfg.cleaning_interval*(1-clean))
                deficits.append(e)
                initial[e.name] = cfg.cleaning_interval-before if flag else 0
    # Convex epigraph of the infimal convolution. For a measured D the optimal
    # z=min(D,delta) leaves D-z in the unit-slope linear tail.
    z=model.addVar(name="huber_core",lb=0,ub=min(DELTA_SECONDS,cap))
    tail=model.addVar(name="huber_tail",lb=0,ub=cap)
    quadratic=model.addVar(name="huber_quadratic",lb=0,ub=DELTA_SECONDS/2)
    model.addCons(range_var==z+tail)
    model.addCons(z*z<=2*DELTA_SECONDS*quadratic)
    raw=initial[range_var.name]
    core=min(raw,DELTA_SECONDS)
    initial[z.name]=core
    initial[tail.name]=max(0.,raw-core)
    initial[quadratic.name]=core*core/(2*DELTA_SECONDS)
    objective=scip.quicksum(terms)/x.N+range_weight*(quadratic+tail)+clean_weight*scip.quicksum(deficits)
    model.addCons(objective >= physical_lower(cfg, range_weight))
    return objective, initial


def _ratio(upper,lower):
    if abs(upper-lower) < 1e-7:
        return 0.
    if lower <= 0:
        return None
    return max(0., (upper-lower)/lower)


def run(mode,source,output,seed=1,seconds=None,gap=.01,backend="D",warm=(),
        schedule="schedule.json",assignment="assignment.json.gz",range_weight=1.,clean_weight=1.):
    if mode not in {"fixed","free","retime"}:
        raise ValueError(mode)
    if min(range_weight,clean_weight,gap)<0 or (seconds is not None and seconds<=0):
        raise ValueError("Check limits and weights")
    sys.path.insert(0,str(cell.BACKENDS[backend]))
    from model import Config, Integrated
    from validate import validate

    start_clock = time.perf_counter()
    source, output = Path(source), Path(output)
    output.mkdir(parents=True,exist_ok=True)
    data,vals = read(source/schedule),cell.values(source/assignment)
    cfg = Config(**data["config"])
    initial = metrics(data,range_weight,clean_weight)
    proof = physical_lower(cfg,range_weight)
    fixed = mode != "free"
    paths = [(source/schedule,source/assignment,data,vals)]
    for path in warm:
        if fixed:
            raise ValueError("Free-structure runs accept additional warm solutions")
        path = Path(path)
        other = read(path/"schedule.json")
        if other["config"]!=data["config"]:
            raise ValueError(f"Warm configuration differs at {path}")
        paths.append((path/"schedule.json",path/"assignment.json.gz",other,cell.values(path/"assignment.json.gz")))
    paths.sort(key=lambda row: (round(metrics(row[2],range_weight,clean_weight)["secondary"],8),metrics(row[2],range_weight,clean_weight)["cmax"]))
    witness_score = metrics(paths[0][2],range_weight,clean_weight)["secondary"]
    if witness_score < proof-cell.EPS:
        raise ValueError("Feasible schedule violates the analytical lower bound")
    proof_gap = _ratio(witness_score,min(proof,witness_score))
    analytic = mode=="free" and proof_gap is not None and proof_gap<=gap+1e-9
    if analytic:
        # Verify the requested common start and the selected optimal/gap witness. The
        # remaining archived candidates provide neither the primal nor the dual bound.
        paths=[row for i,row in enumerate(paths) if i==0 or row[0]==source/schedule]
    x = Integrated(cfg)
    m = x.model
    native = list(m.getVars(transformed=False))
    original_rows = m.getNConss()
    cell.scip_settings(m,dict(n=x.N,seed=seed,seconds=seconds,gap=gap),output)
    m.setRealParam("numerics/feastol",1e-8)
    def compare(a,b):
        if any(abs(a[k]-b[k])>cell.EPS for k in a):
            raise ValueError(f"Archived schedule and its assignment disagree: {a} / {b}")
    accepted = []
    checked_paths = []
    for index,(sched_path, vals_path, sched, vs) in enumerate(paths):
        ref = metrics(sched,range_weight,clean_weight)
        # The archived A command used SCIP's 1e-6 tolerance. Its role in the
        # analytical B proof is to identify the common start; a different
        # witness supplies the upper bound and is checked at 1e-8.
        tolerance = 1e-6 if analytic and index>0 else 1e-8
        m.setRealParam("numerics/feastol",tolerance)
        old=cell.solution(x,vs)
        snapped=False
        if not m.checkSol(old,original=True,completely=True,printreason=False):
            m.freeSol(old)
            vs={k:(float(round(v)) if abs(v-round(v))<=1.1e-6 else v) for k,v in vs.items()}
            old=cell.attach(x,vs)
            snapped=True
        decoded = x.result(solution=old)
        compare(ref,metrics(decoded,range_weight,clean_weight))
        replay = validate(decoded)
        if not replay["valid"]:
            raise ValueError(replay["errors"][:3])
        m.freeSol(old)
        accepted.append(dict(schedule=str(sched_path.resolve()),assignment=str(vals_path.resolve()),
                             schedule_sha256=sha(sched_path),assignment_sha256=sha(vals_path),metrics=ref,
                             native_feastol=tolerance,near_integer_repair=snapped))
        checked_paths.append((sched_path,vals_path,decoded if snapped else sched,vs))
    paths=checked_paths
    m.setRealParam("numerics/feastol",1e-8)
    if analytic:
        best_schedule,best_assignment,decoded,checked_vals=paths[0]
        replay=validate(decoded)
        if not replay["valid"]:
            raise ValueError(replay["errors"][:3])
        measured=metrics(decoded,range_weight,clean_weight)
        save(output/"assignment.json.gz",cell.sparse(checked_vals))
        save(output/"schedule.json",decoded)
        m.freeProb()
        record=dict(status="analytic_optimal" if abs(proof-witness_score)<=1.e-7 else "analytic_gap",
                    upper=witness_score,lower=proof,gap=proof_gap,seconds=0.,
                    wall_seconds=time.perf_counter()-start_clock,nodes=0,native_dual=None,physical_lower=proof,
                    proof="Terminal-wafer count by finite 2x2 chain, residence spread bound and minimum of the Huber epigraph")
        result=dict(mode=mode,backend=backend,scope="all input-feasible structures",seed=seed,target_gap=gap,
                    weights=dict(range=range_weight,clean=clean_weight),initial=initial,measured=measured,
                    eligible=True,record=record,parents=accepted,original_rows=original_rows,
                    replayed_rows=original_rows,replay=replay,
                    files={k:sha(output/k) for k in ("schedule.json","assignment.json.gz")})
        save(output/"result.json",result)
        return result
    if fixed:
        for v in native:
            if v.vtype()!="CONTINUOUS" and not v.name.startswith("sync_"):
                value=round(vals.get(v.name,0))
                m.chgVarLb(v,value)
                m.chgVarUb(v,value)
        if mode=="fixed":
            m.addCons(x.cmax<=initial["cmax"]+1e-6)
    # The best incumbent is sufficient for the warm start. Every extra input has
    # already been replayed above; the free model retains all feasible structures.
    _,_,best_data,best_values = paths[0]
    expression, extra = objective_terms(x,best_values,fixed,range_weight,clean_weight)
    m.setObjective(expression,"minimize")
    warm_sol=cell.attach(x,best_values|extra)
    warm_score=metrics(best_data,range_weight,clean_weight)["secondary"]
    if abs(m.getSolObjVal(warm_sol)-warm_score)>cell.EPS:
        raise ValueError("New solver objective and warm score disagree")
    if not m.addSol(warm_sol):
        raise ValueError("Checked original warm solution was rejected")
    m.optimize()
    raw_upper,raw_lower=m.getPrimalbound(),m.getDualbound()
    status,seconds_solved,nodes=str(m.getStatus()),m.getSolvingTime(),m.getNNodes()
    best=m.getBestSol()
    if best is None:
        raise ValueError("Lost verified feasible solution")
    answer={v.name:m.getSolVal(best,v) for v in native}
    m.freeTransform()
    original=cell.solution(x,answer)
    decoded=x.result(solution=original)
    measured=metrics(decoded,range_weight,clean_weight)
    answer[x.cmax.name]=measured["cmax"]
    m.freeSol(original)
    m.freeProb()
    checked=cell.lift(cfg,answer,None,rebuild=True)
    if not checked or not checked[3]["valid"]:
        raise ValueError("Final original-model replay failed")
    decoded, assignment_data, _, replay, rows=checked
    compare(measured,metrics(decoded,range_weight,clean_weight))
    if abs(measured["secondary"]-raw_upper)>cell.EPS or (mode=="fixed" and measured["cmax"]>initial["cmax"]+cell.EPS):
        raise ValueError("Archived and solver objectives disagree")
    lower=max(raw_lower,proof)
    if lower>measured["secondary"]+cell.EPS:
        raise ValueError("Invalid global or native lower bound")
    gap_value=_ratio(measured["secondary"],min(measured["secondary"],lower))
    save(output/"schedule.json",decoded)
    save(output/"assignment.json.gz",assignment_data)
    result=dict(mode=mode,backend=backend,scope={"fixed":"primary structure with makespan cap",
                       "retime":"fixed structure without makespan cap","free":"all input-feasible structures"}[mode],
                weights=dict(range=range_weight,clean=clean_weight),initial=initial,measured=measured,
                eligible=gap_value is not None and gap_value<=gap+1e-8,seed=seed,target_gap=gap,
                record=dict(status=status,upper=measured["secondary"],lower=lower,gap=gap_value,seconds=seconds_solved,
                    wall_seconds=time.perf_counter()-start_clock,nodes=nodes,native_dual=raw_lower,
                    physical_lower=proof,solver_upper=raw_upper),
                parents=accepted,original_rows=original_rows,replayed_rows=rows,replay=replay,
                files={k:sha(output/k) for k in ("schedule.json","assignment.json.gz")})
    save(output/"result.json",result)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("fixed","free","retime"),required=True)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seed",type=int,default=1)
    parser.add_argument("--gap",type=float,default=.01)
    parser.add_argument("--seconds",type=float)
    parser.add_argument("--backend",choices=("D","E"),default="D")
    parser.add_argument("--warm",type=Path,action="append",default=[])
    parser.add_argument("--schedule",default="schedule.json")
    parser.add_argument("--assignment",default="assignment.json.gz")
    parser.add_argument("--range-weight",type=float,default=1.)
    parser.add_argument("--clean-weight",type=float,default=1.)
    run(**vars(parser.parse_args()))
