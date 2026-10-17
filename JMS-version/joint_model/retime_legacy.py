"""Reuse discrete legacy decisions; recompute physically valid event times."""
from pathlib import Path
import argparse,json,time
from model import Config,Integrated
from seed import construct,constrain_seed
from validate import validate
from run_experiments import fix_structure,dump,finite,assets,digest
from joint_algorithms import improve_skeleton

def retime(source,output,budget=30):
    started=time.monotonic();source=Path(source);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    old=json.loads(source.read_text(encoding='utf-8-sig'));cfg=Config(**old['config'])
    cfg.max_pairs=len(old['pairs']);cfg.max_cycles=max(c['index'] for c in old['cycles'])+1
    initial=construct(cfg,old);dump(out/'initial_schedule.json',initial)
    dump(out/'manifest.json',dict(source=str(source.resolve()),source_sha256=digest(source),assets=assets(),retimer_sha256=digest(Path(__file__)),optimization_budget=budget,scope='Fixed legacy pairing, chamber assignment and cycle structure; new atomic timing'))
    x=Integrated(cfg);m=x.model;fix_structure(x,initial)
    fixed=constrain_seed(x,initial);m.setObjective(0,'minimize');m.setRealParam('limits/time',30);m.optimize()
    if not m.getNSols():raise RuntimeError('Initial schedule MILP completion failed')
    sol=m.getBestSol();values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
    m.freeTransform()
    for v,lb,ub in fixed:m.chgVarLb(v,lb);m.chgVarUb(v,ub)
    values,levels=improve_skeleton(x,values,budget);dump(out/'timing_levels.json',levels)
    sol=m.createSol()
    for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
    if not m.checkSol(sol,printreason=False,completely=True):raise RuntimeError('Retimed assignment failed MILP check')
    m.addSol(sol);m.setObjective(x.primary_objective,'minimize');m.setRealParam('limits/time',.01);m.optimize()
    result=x.result();result['validation']=validate(result)
    result.update(experiment_scope='reused_structure_retimed',full_candidate_space=False,primary_bound=None,global_optimality_claim=False,legacy_reuse=old.get('legacy_reuse'),elapsed_seconds=time.monotonic()-started)
    # Conditional solver bounds must not enter comparisons over unrestricted pairings.
    result['conditional_dual_bound']=result.pop('dual_bound',None)
    result['conditional_gap']=result.pop('gap',None)
    dump(out/'result.json',finite(result));m.freeProb()
    if not result['validation']['valid']:raise RuntimeError(result['validation']['errors'])
    return dict(output=str(out),cmax=result['cmax'],valid=True,seconds=result['elapsed_seconds'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--time-limit',type=float,default=30)
    a=p.parse_args();print(json.dumps(retime(a.source,a.output,a.time_limit),ensure_ascii=False))
