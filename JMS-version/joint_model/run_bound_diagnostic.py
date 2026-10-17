"""Bound-strengthened root-search diagnostic; preserves existing experiments."""
from pathlib import Path
import argparse,json,time,re
from model import Config,Integrated,products_from_load_ports
from validate import validate
from run_experiments import assets,digest,dump,finite
from run_matched_supplement import output_lock,archive_incomplete
from joint_algorithms import install

def route_bound(cfg):
    ws=products_from_load_ports(cfg.load_ports);durations=[cfg.full_time if w.mode=='4x1' else 2*cfg.mix_time for w in ws]
    # Last product to finish alignment still traverses LL, PM, and its return route.
    al_first=cfg.atr_handling+cfg.atr_travel
    al_work=len(ws)*(2*cfg.atr_handling+cfg.alignment)
    suffix=2*cfg.atr_travel+3*cfg.atr_handling+cfg.pump+4*cfg.handling+2*cfg.vtr_travel+min(durations)+cfg.vent
    return al_first+al_work+suffix

def run(source,output,limit=120,resume=False):
    source=Path(source);out=Path(output)
    r=json.loads((source/'result.json').read_text());assert validate(r)['valid']
    cfg=Config(**r['config']);vfile=source/'variables.json'
    if cfg.max_pairs or cfg.max_cycles:raise ValueError('Diagnostic requires the full candidate configuration')
    protocol=dict(source=str(source.resolve()),result_sha256=digest(source/'result.json'),variables_sha256=digest(vfile),assets=assets(),diagnostic_sha256=digest(Path(__file__)),time_limit=limit)
    with output_lock(out):
        p=out/'protocol.json'
        if p.exists():
            if json.loads(p.read_text())!=protocol:raise RuntimeError('Diagnostic protocol changed; use a new output')
        else:dump(p,protocol)
        for method in ['scip','proposed']:
            dest=out/method
            if (dest/'result.json').exists():
                saved=json.loads((dest/'result.json').read_text())
                if not validate(saved)['valid']:raise RuntimeError('Saved diagnostic failed replay')
                print('REUSE '+str(dest),flush=True);continue
            if dest.exists():
                if not resume:raise RuntimeError('Use --resume for interrupted diagnostics')
                archive_incomplete(out,dest)
            dest.mkdir();started=time.monotonic();x=Integrated(cfg);m=x.model
            m.setIntParam('randomization/randomseedshift',1);m.setIntParam('parallel/maxnthreads',1);m.setRealParam('limits/memory',24000)
            values=json.loads(vfile.read_text())['values'];sol=m.createSol()
            for v in m.getVars(transformed=False):
                if v.name not in values:raise ValueError('Warm start has different variable inventory')
                m.setSolVal(sol,v,values[v.name])
            if not m.checkSol(sol,printreason=False,completely=True):raise RuntimeError('Warm start failed full-model check')
            m.addSol(sol)
            lb=route_bound(cfg);ub=r['cmax']+1e-6
            if lb>ub+1e-4:raise RuntimeError('Analytical lower bound exceeds a valid witness')
            m.addCons(x.cmax>=lb);m.addCons(x.cmax<=ub)
            agent,policy=install(m,method,1);m.setIntParam('separating/maxroundsroot',1);m.setIntParam('separating/maxrounds',0)
            m.setLogfile(str(dest/'solver.log'));m.setRealParam('limits/time',limit);m.optimize()
            result=x.result();result['validation']=validate(result);result.update(experiment_scope='validated_incumbent_and_route_bound_diagnostic',primary_bound=result['dual_bound'],primary_status=result['status'],method=method,analytic_route_bound=lb,initial_cmax=r['cmax'],elapsed_seconds=time.monotonic()-started)
            telemetry=agent.get_telemetry() if agent is not None else {}
            dump(dest/'telemetry.json',telemetry)
            dump(dest/'search.json',dict(nodes=m.getNNodes(),lp_solves=m.getNLPs(),lp_iterations=m.getNLPIterations(),callbacks=telemetry.get('callback_calls'),seconds=m.getSolvingTime(),policy=policy))
            dump(dest/'result.json',finite(result));m.freeProb()
            if not result['validation']['valid']:raise RuntimeError('Diagnostic result failed replay')
            print(json.dumps(dict(method=method,cmax=result['cmax'],bound=result['primary_bound'],callbacks=telemetry.get('callback_calls'))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--time-limit',type=float,default=120);p.add_argument('--resume',action='store_true');a=p.parse_args();run(a.source,a.output,a.time_limit,a.resume)
