"""CP-SAT exact search with checked translation and original-model replay.

Main time limit defaults to infinity. Integer-timing coverage and final full
model certification are separate proof obligations, never inferred from a plot.
"""
from pathlib import Path
from dataclasses import asdict,replace
from datetime import datetime,timezone
import argparse,json,sys,shutil,time,math
import ortools
from ortools.sat.python import cp_model
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'JMS-version/joint_model'))
from model import Config,Integrated
from seed import constrain_seed
from validate import validate
from run_experiments import dump,digest,assets,finite
from incumbent_sublevel import capacity_certificate,strengthen
from terminal_cleanup_bound import cleanup_certificate
from cycle_work_bounds import add_cycle_work_bounds
from optimality_runtime import certificate_asset_changes
from integer_timing_export import export_model
from pair_label_symmetry import canonical_seed,add_label_symmetry


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--source',required=True);p.add_argument('--certificate',required=True)
    p.add_argument('--output',required=True);p.add_argument('--probe-seconds',type=float,default=0)
    p.add_argument('--workers',type=int,default=2);p.add_argument('--memory-mb',type=int,default=6000)
    a=p.parse_args()
    if a.probe_seconds<0 or a.workers<1 or a.memory_mb<=0:p.error('Invalid resource limit')
    source=Path(a.source).resolve();certpath=Path(a.certificate).resolve();out=Path(a.output).resolve()
    data=json.loads(source.read_text(encoding='utf-8-sig'));cert=json.loads(certpath.read_text(encoding='utf-8-sig'))
    if not cert['accepted'] or not cert['full_candidate_space'] or cert['source_sha256']!=digest(source):raise ValueError('Matching original-model certificate required')
    changes=certificate_asset_changes(cert['assets'],assets());physical=validate(data)
    if not physical['valid']:raise ValueError(physical['errors'])
    cfg=Config(**data['config']);upper=physical['product_return_cmax']
    if abs(upper-round(upper))>1e-7:raise ValueError('Integer initialization upper bound required')
    upper=round(upper);capacity=capacity_certificate(cfg,upper);cleanup=cleanup_certificate(cfg,upper,capacity)
    compact=replace(cfg,max_pairs=capacity['pairs'],max_cycles=capacity['cycles_per_chamber'],horizon=cleanup['normal_form_horizon'])
    out.mkdir(parents=True,exist_ok=False)
    scripts={}
    for name in ('solve_cpsat_sublevel.py','integer_timing_export.py','incumbent_sublevel.py','terminal_cleanup_bound.py','cycle_work_bounds.py','pure2_block_certificate.py','optimality_runtime.py','pair_label_symmetry.py'):
        path=Path(__file__).with_name(name);shutil.copy2(path,out/name);scripts[name]=digest(path)
    manifest=dict(source=str(source),source_sha256=digest(source),certificate=str(certpath),
         certificate_sha256=digest(certpath),assets=assets(),scripts=scripts,config=asdict(cfg),
         capacity_certificate=capacity,cleanup_certificate=cleanup,ortools=ortools.__version__,
         workers=a.workers,memory_mb=a.memory_mb,main_time_limit=a.probe_seconds or None,
         random_seed=1,started_utc=datetime.now(timezone.utc).isoformat(),reporting_helper_changes=changes)
    dump(out/'manifest.json',manifest)
    print('BUILD unchanged physical model with proven sublevel and cleanup bounds',flush=True)
    x=Integrated(compact);m=x.model;m.hideOutput(False);m.setRealParam('numerics/feastol',1e-10)
    m.setRealParam('limits/memory',a.memory_mb);m.setRealParam('limits/time',120);m.setLogfile(str(out/'initialization.log'))
    cuts=strengthen(x,upper,capacity);cuts['cycle_work']=add_cycle_work_bounds(x,upper,capacity);dump(out/'strengthening.json',cuts)
    data,label_map=canonical_seed(data,[w.identifier for w in x.products])
    if not validate(data)['valid']:raise RuntimeError('Label permutation failed physical replay')
    cuts['label_symmetry']=add_label_symmetry(x);dump(out/'strengthening.json',cuts)
    dump(out/'initial_label_map.json',label_map)
    fixed=constrain_seed(x,data)
    for v,lo,hi in fixed:
        if v.vtype()=='CONTINUOUS' and v.getLbOriginal()>upper+1e-7:m.chgVarLb(v,lo);m.chgVarUb(v,hi)
    m.setObjective(0,'minimize');m.optimize()
    if not m.getNSols():raise RuntimeError('Initialization completion failed')
    seed=x.result(m.getBestSol());seed['config']=asdict(cfg);seed['validation']=validate(seed)
    if not seed['validation']['valid']:raise RuntimeError(seed['validation']['errors'])
    values={v.name:m.getSolVal(m.getBestSol(),v) for v in m.getVars(transformed=False)}
    dump(out/'initialization.json',finite(seed));m.freeTransform()
    for v,lo,hi in fixed:m.chgVarLb(v,lo);m.chgVarUb(v,hi)
    m.setObjective(x.cmax,'minimize')
    print('EXPORT every original linear row; auditing integer timing',flush=True)
    cp,vmap,audit=export_model(x,values);dump(out/'integer_export_audit.json',audit)
    cp.export_to_file(str(out/'model.pb'));manifest['cp_model_sha256']=digest(out/'model.pb');dump(out/'manifest.json',manifest)
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=a.workers
    solver.parameters.random_seed=1;solver.parameters.max_memory_in_mb=a.memory_mb
    solver.parameters.log_search_progress=True
    if a.probe_seconds:solver.parameters.max_time_in_seconds=a.probe_seconds
    log=(out/'solver.log').open('w',encoding='utf-8')
    def logging(line):log.write(line if line.endswith('\n') else line+'\n');log.flush()
    solver.log_callback=logging
    state=dict(upper=upper,lower=max(cuts['al_work_tail_bound'],cuts['cycle_work'].get('global_work_lower_bound',0)),
               status='searching',seconds=0,eta='unknown; exact proof pending')
    begun=time.monotonic()
    def bound(value):
        state.update(lower=value,seconds=time.monotonic()-begun);dump(out/'progress.json',finite(state))
    solver.best_bound_callback=bound
    variables=m.getVars(transformed=False)
    def materialize(value):
        sol=m.createSol()
        for v in variables:m.setSolVal(sol,v,value(vmap[v.name]))
        okay=m.checkSol(sol,printreason=False,completely=True,original=True)
        result=x.result(sol);result['config']=asdict(cfg);result['validation']=validate(result)
        result.update(sublevel_model_check=bool(okay),experiment_scope='integer_exact_sublevel',
             full_candidate_space=False,global_optimality_claim=False,original_model_check=False)
        m.freeSol(sol);return result
    class Solutions(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            state.update(upper=self.objective_value,lower=self.best_objective_bound,seconds=self.wall_time,
                         branches=self.num_branches,conflicts=self.num_conflicts)
            result=materialize(self.value)
            if not result['sublevel_model_check'] or not result['validation']['valid']:
                dump(out/'rejected_solution.json',finite(result));raise RuntimeError('CP incumbent failed original-row/physical replay')
            dump(out/'checkpoint.json',finite(result));dump(out/'progress.json',finite(state))
    dump(out/'progress.json',state)
    print('SEARCH CP-SAT; no structural initialization fixes remain; ETA unknown',flush=True)
    status=solver.solve(cp,Solutions());log.close()
    (out/'response.pb').write_bytes(solver.response_proto.SerializeToString())
    manifest['cp_response_sha256']=digest(out/'response.pb');dump(out/'manifest.json',manifest)
    feasible=status in (cp_model.OPTIMAL,cp_model.FEASIBLE)
    result=materialize(solver.value) if feasible else seed
    lower=solver.best_objective_bound
    result.update(backend='CP-SAT',backend_status=solver.status_name(status),
        primary_status='optimal' if status==cp_model.OPTIMAL else 'not_certified',primary_bound=lower,
        primary_gap=abs(result['cmax']-lower)/max(abs(lower),1e-10),capacity_certificate=capacity,
        cleanup_certificate=cleanup,integer_timing_audit=audit,full_candidate_space=False,
        global_optimality_claim=False,original_model_check=False,experiment_scope='integer_exact_sublevel')
    dump(out/'result.json',finite(result))
    if feasible:dump(out/'variables.json',dict(values={name:solver.value(v) for name,v in vmap.items()}))
    dump(out/'finished.json',dict(status=solver.status_name(status),sublevel_optimal=status==cp_model.OPTIMAL,
          physical_valid=result['validation']['valid'],sublevel_model_check=result.get('sublevel_model_check',False),
          paper_certified=False,branches=solver.num_branches,wall_seconds=solver.wall_time))
    print('CP SEARCH ENDED '+solver.status_name(status)+'; final full-model certification pending',flush=True)
    m.freeProb()


if __name__=='__main__':main()
