"""Execute one manuscript experimental condition in an isolated process."""
import argparse
from dataclasses import replace
import gc
import math
from pathlib import Path
import sys
import time
import traceback

from protocol import HERE,JMS,ROOT,OUT,LEVELS,TUNING,read,rel,save,sha
sys.path.insert(0,str(HERE.parent/'sublevel_bounds_20261120'))
sys.path.insert(0,str(HERE.parent/'finite_budget_20261116'))
from bounds import capacity,lock_bound,strengthen
from finite_budget import BACKENDS,physical_metrics
from design import pick,sparse

EPS=2e-4


def values(path):
    d=read(path)
    if 'values' in d: return d['values']
    if d['default']!=0: raise ValueError('Unknown assignment encoding')
    return d['nonzero']


def solution(x,vals):
    m=x.model
    s=m.createSol()
    for v in m.getVars(transformed=False):
        m.setSolVal(s,v,vals.get(v.name,0.))
    return s


def attach(x,vals):
    s=solution(x,vals)
    if not x.model.checkSol(s,original=True,completely=True,printreason=True):
        raise ValueError('Original assignment rejected')
    return s


def metrics(data):
    from validate import validate
    replay=validate(data)
    if not replay['valid']: raise ValueError(str(replay['errors'][:3]))
    result=physical_metrics(data)
    if abs(replay['product_return_cmax']-result['cmax'])>EPS:
        raise ValueError('Replay and product returns disagree')
    return result,replay


def lift(cfg,vals,compact_q,rebuild=False):
    import model
    x=model.Integrated(cfg)
    m=x.model
    if compact_q and compact_q<x.Q:
        for c in cfg.chambers:
            vals[f'empty_boundary_{c}_{compact_q}']=cfg.horizon
    s=solution(x,vals)
    variables=m.getVars(transformed=False)
    vmap={v.name:v for v in variables}
    val=lambda v:m.getSolVal(s,v)
    if rebuild:
        m.setSolVal(s,x.max_wait,max(val(w) for w in x.waits))
        for c in cfg.chambers:
            for q in range(2,x.Q):
                active=val(x.keep[c,q])>.5 and val(x.keep[c,q-1])>.5
                delta=abs(val(x.cy.start[c,q])-2*val(x.cy.start[c,q-1])+val(x.cy.start[c,q-2]))
                m.setSolVal(s,vmap[f'rhythm_{c}_{q}'],max(0.,delta-(0 if active else x.M)))
    good=m.checkSol(s,original=True,completely=True,printreason=False)
    out=None
    if good:
        data=x.result(solution=s)
        measure,replay=metrics(data)
        m.setSolVal(s,x.cmax,measure['cmax'])
        if not m.checkSol(s,original=True,completely=True): raise ValueError('Physical Cmax tightening failed')
        data['cmax']=measure['cmax']
        out=(data,sparse({v.name:val(v) for v in variables}),measure,replay,m.getNConss())
    m.freeSol(s)
    m.freeProb()
    return out


def certify_start(cfg,data,vals):
    checked=lift(cfg,dict(vals),None)
    if not checked: raise ValueError('Initial solution fails full-domain native constraints')
    for field in ('cmax','secondary'):
        if abs(checked[2][field]-physical_metrics(data)[field])>EPS:
            raise ValueError('Source assignment and schedule physical metrics differ: '+field)
    return checked


def get_source(spec,task):
    key=task['start']
    if key in spec['inputs']:
        d=spec['inputs'][key]
        s,v=ROOT/d['schedule'],ROOT/d['assignment']
    else:
        folder=OUT/'runs'/key
        d=read(folder/'evidence.json')
        if not d['valid']: raise ValueError('Invalid parent')
        s,v=folder/'schedule.json',folder/'assignment.json.gz'
    if sha(s)!=d['schedule_sha256'] or sha(v)!=d['assignment_sha256']:
        raise ValueError('Changed stage input')
    return read(s),values(v),d


def scip_settings(m,task,folder):
    m.setIntParam('parallel/maxnthreads',1)
    m.setIntParam('lp/threads',1)
    m.setIntParam('randomization/randomseedshift',task['seed'])
    m.setIntParam('timing/clocktype',2)
    m.setRealParam('limits/time',task['seconds'] if task.get('seconds') is not None else m.infinity())
    m.setRealParam('limits/gap',task.get('gap') or 0.)
    m.setRealParam('limits/absgap',0.)
    m.setRealParam('limits/memory',6500 if task['n']==16 else 2300)
    m.setLogfile(str(folder/'solver.log'))
    m.hideOutput()


def primary(task,cfg,data,vals,folder,input_sha):
    import model
    start,replay=metrics(data)
    ub=start['cmax']
    lb=lock_bound(cfg)['lower']
    tau=task.get('gap')
    fixed=task.get('structure')=='fixed'
    scope='fixed_structure_Cmax' if fixed else 'global_product_Cmax'
    measured=max(0.,ub-lb)/lb
    if lb>ub+EPS: raise ValueError('Resource bound exceeds feasible upper')
    if measured<=(tau or 0.)+1e-10:
        checked=certify_start(cfg,data,vals)
        return checked,dict(scope=scope,lower=lb,upper=ub,gap=measured,gate=True,seconds=0.,
                   status='analytic_gap',policy_calls=0,initial_proof=True,engine=task['kind'])
    upper=math.ceil(ub)
    reduced=task.get('bounds',True)
    plan=capacity(cfg,upper) if reduced else None
    x=model.Integrated(replace(cfg,max_pairs=plan['pairs'],max_cycles=plan['cycles']) if reduced else cfg)
    m=x.model
    if reduced: strengthen(x,plan,data,upper)
    else:
        m.addCons(x.cmax>=lb)
        m.addCons(x.cmax<=upper+1e-6)
    if fixed:
        from seed import constrain_seed
        constrain_seed(x,data,times=False)
    q=x.Q
    candidate=None
    calls=None
    policy=None
    search={}
    engine=task['kind']
    checkpoint=folder/'resume.json'
    previous=read(checkpoint) if tau is not None and checkpoint.is_file() else {}
    if previous:
        if previous['input_sha256']!=input_sha: raise ValueError('Changed resumable input')
        lb=max(lb,previous['bound'])
        m.addCons(x.cmax>=lb-1e-7)
    if engine=='cp':
        from ortools.sat.python import cp_model
        from project import export
        cp,vm,audit=export(x,vals)
        m.freeProb()
        del m,x
        gc.collect()
        solver=cp_model.CpSolver()
        solver.parameters.num_search_workers=1
        solver.parameters.random_seed=task['seed']
        solver.parameters.max_memory_in_mb=1800 if task['n']==16 else 768
        if task['seconds'] is not None: solver.parameters.max_time_in_seconds=task['seconds']
        if tau is not None: solver.parameters.relative_gap_limit=tau/(1+tau)
        solver.parameters.log_search_progress=True
        solver.parameters.log_to_stdout=False
        def bound_event(b):
            if tau is not None and lb<b<=ub:
                save(checkpoint,dict(input_sha256=input_sha,bound=b))
        solver.best_bound_callback=bound_event
        with (folder/'solver.log').open('w',encoding='utf-8',buffering=1) as stream:
            solver.log_callback=lambda s:stream.write(s.rstrip()+'\n')
            status=solver.solve(cp)
        if status in (cp_model.MODEL_INVALID,cp_model.INFEASIBLE): raise ValueError('Projection excluded source')
        if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            candidate={n:solver.value(v) for n,v in vm.items() if solver.value(v)}
        lb=max(lb,solver.best_objective_bound)
        elapsed=solver.wall_time
        label=solver.status_name(status)
        search=dict(cp_rows=len(cp.proto.constraints),cp_variables=len(vm),row_export=audit,branches=solver.num_branches)
        del vm,cp,solver
    else:
        scip_settings(m,task,folder)
        if task['method']!='default':
            sys.path.insert(0,str(HERE.parent/'component_gap_restore_20261119'))
            from component import POLICIES,policy_on_cpu
            method=POLICIES[task['method']]
            agent,policy=policy_on_cpu(m,method[0],method,task['seed'],task['train'])
        else: agent=None
        m.setObjective(x.cmax,'minimize')
        m.addSol(attach(x,vals))
        if tau is not None:
            from scip_imports import scip
            class BoundEvent(scip.Eventhdlr):
                def eventinit(self): self.model.catchEvent(scip.SCIP_EVENTTYPE.DUALBOUNDIMPROVED,self)
                def eventexit(self): self.model.dropEvent(scip.SCIP_EVENTTYPE.DUALBOUNDIMPROVED,self)
                def eventexec(self,event):
                    b=self.model.getDualbound()
                    if lb<b<=ub: save(checkpoint,dict(input_sha256=input_sha,bound=b))
            m.includeEventhdlr(BoundEvent(),'global_bound','validated restart bound')
        m.optimize()
        elapsed=m.getSolvingTime()
        lb=max(lb,m.getDualbound())
        label=str(m.getStatus())
        best=m.getBestSol()
        if best:
            candidate={v.name:m.getSolVal(best,v) for v in m.getVars(transformed=False)}
        tel=agent.get_telemetry() if agent is not None else {}
        if agent is not None: save(folder/'cutsel.json',tel)
        calls=tel.get('callback_calls',0)
        search=dict(nodes=m.getNNodes(),lp_iterations=m.getNLPIterations(),lp_solves=m.getNLPs())
        m.freeProb()
        del m,x
    gc.collect()
    checked=lift(cfg,candidate,q,rebuild=engine=='cp') if candidate is not None else None
    accepted=checked is not None and checked[2]['cmax']<=ub+EPS
    if not accepted: checked=certify_start(cfg,data,vals)
    ub=checked[2]['cmax']
    if lb>ub+EPS: raise ValueError('Bound exceeds validated feasible solution')
    gap=max(0.,ub-lb)/lb
    gate=(gap<=tau+1e-9) if tau is not None else (gap<1e-9)
    if tau is not None and not gate: raise ValueError(f'Gap stop without verified gap {gap} from {label}')
    return checked,dict(engine=engine,scope=scope,lower=lb,upper=ub,gap=gap,gate=gate,status=label,seconds=elapsed,
                        policy_calls=calls,policy=policy,capacity=plan,search=search,accepted_candidate=accepted)


def other(task,cfg,data,vals,folder):
    import model
    from scip_imports import scip
    start,_=metrics(data)
    x=model.Integrated(cfg)
    m=x.model
    scip_settings(m,task,folder)
    vs=m.getVars(transformed=False)
    native=attach(x,vals)
    init=physical_metrics(x.result(solution=native))
    if any(abs(init[k]-start[k])>EPS for k in ('cmax','secondary')):
        raise ValueError('Initial schedule and assignment disagree')
    m.freeSol(native)
    kind=task['kind']
    if kind=='prep':
        from joint_algorithms import improve_skeleton
        dense={v.name:vals.get(v.name,0.) for v in vs}
        improved,trace=improve_skeleton(x,dense,task['seconds'])
        elapsed=sum(row['seconds'] for row in trace)
        record=dict(engine='SCIP SPBS',scope='initialization',trace=trace,seconds=elapsed,status='completed')
        result=improved
    else:
        byname={v.name:v for v in vs}
        active=[]
        physical_epigraph={}
        if kind=='secondary':
            for v in vs:
                if v.vtype()!='CONTINUOUS' and not v.name.startswith('sync_'):
                    bit=round(vals.get(v.name,0.))
                    m.chgVarLb(v,bit)
                    m.chgVarUb(v,bit)
            m.addCons(x.cmax<=start['cmax']+1e-6)
        for c in cfg.chambers:
            for q in range(2,x.Q):
                v=byname[f'rhythm_{c}_{q}']
                k=x.keep[c,q]
                h=x.keep[c,q-1]
                active_input=vals.get(k.name,0.)>.5 and vals.get(h.name,0.)>.5
                if kind=='secondary':
                    if active_input: active.append(v)
                else:
                    z=m.addVar(lb=0,ub=cfg.horizon,name=f'physical_pitch_{c}_{q}')
                    m.addCons(z>=v-cfg.horizon*(2-k-h))
                    active.append(z)
                    if active_input:
                        physical_epigraph[z.name]=abs(vals.get(x.cy.start[c,q].name,0.)-2*vals.get(x.cy.start[c,q-1].name,0.)+vals.get(x.cy.start[c,q-2].name,0.))
        weight=task.get('weight',25)
        score=scip.quicksum(x.waits)+10*x.max_wait+weight*scip.quicksum(active)
        scale_c=max(1.,start['cmax'])
        scale_b=max(1.,start['secondary'])
        objective=score if kind=='secondary' else x.cmax/scale_c+task['rho']*score/scale_b
        m.setObjective(objective,'minimize')
        warm=solution(x,vals|physical_epigraph)
        val=lambda v:m.getSolVal(warm,v)
        m.setSolVal(warm,x.cmax,start['cmax'])
        m.setSolVal(warm,x.max_wait,start['wait_max'])
        for c in cfg.chambers:
            for q in range(2,x.Q):
                a=val(x.keep[c,q])>.5 and val(x.keep[c,q-1])>.5
                d=abs(val(x.cy.start[c,q])-2*val(x.cy.start[c,q-1])+val(x.cy.start[c,q-2]))
                m.setSolVal(warm,byname[f'rhythm_{c}_{q}'],max(0.,d-(0 if a else x.M)))
        if not m.checkSol(warm,completely=True,original=True,printreason=True): raise ValueError('Objective warm start rejected')
        m.addSol(warm)
        m.optimize()
        lb=m.getDualbound()
        ub=m.getPrimalbound()
        elapsed=m.getSolvingTime()
        status=str(m.getStatus())
        best=m.getBestSol()
        if best is None: raise ValueError('Validated incumbent disappeared')
        result={v.name:m.getSolVal(best,v) for v in vs}
        gap=max(0.,ub-lb)/max(1e-12,min(abs(ub),abs(lb))) if lb>0 else (0. if abs(ub-lb)<1e-8 else None)
        if task.get('gap') is not None and (gap is None or gap>task['gap']+1.e-9 or status not in ('gaplimit','optimal')):
            raise ValueError('Secondary gap not certified')
        record=dict(scope='fixed_structure_secondary' if kind=='secondary' else 'normalized_joint',
                    engine='SCIP',status=status,lower=lb,upper=ub,gap=gap,seconds=elapsed,weight=weight,
                    normalization={'cmax':scale_c,'secondary':scale_b},gate=task.get('gap') is not None)
    m.freeProb()
    del m,x,vs
    gc.collect()
    checked=lift(cfg,result,None)
    if checked is None: raise ValueError('Final assignment failed original rows')
    measure=checked[2]
    if kind=='secondary':
        physical=measure['wait_sum']+10*measure['wait_max']+weight*measure['rhythm']
        if abs(physical-ub)>EPS or measure['cmax']>start['cmax']+EPS: raise ValueError('Secondary objective or cap mismatch')
    if kind=='weighted':
        physical=measure['cmax']/scale_c+task['rho']*measure['secondary']/scale_b
        if abs(physical-ub)>EPS: raise ValueError('Joint objective differs from replayed events')
    return checked,record


def selected_levels(spec):
    grid={}
    for c in TUNING:
        for a in LEVELS:
            for b in LEVELS:
                e=read(OUT/'runs'/f'{c}__grid_B_{a}_{b}'/'evidence.json')
                if not e['valid'] or not e['record']['gate']: raise ValueError('Incomplete threshold grid')
                grid[c,a,b]=e
    return pick(grid)


def run(task_key):
    import psutil
    spec=read(OUT/'protocol.json')
    task=dict(spec['tasks'][task_key])
    folder=OUT/'runs'/task_key
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'evidence.json').exists(): return
    case=spec['cases'][task['case']]
    sys.path.insert(0,str(BACKENDS[case['backend']]))
    import model
    cfg=model.Config(**case['config'])
    started=time.monotonic()
    data,vals,src=get_source(spec,task)
    if task['kind']=='selected':
        a,b=selected_levels(spec)
        task.update(kind=task['engine'],gap=LEVELS[a])
        checked,one=primary(task,cfg,data,vals,folder,src['assignment_sha256'])
        stageA=folder/'A'
        stageA.mkdir(exist_ok=True)
        save(stageA/'assignment.json.gz',checked[1])
        save(stageA/'schedule.json',checked[0])
        save(stageA/'evidence.json',dict(record=one,metrics=checked[2],assignment_sha256=sha(stageA/'assignment.json.gz'),
                                        schedule_sha256=sha(stageA/'schedule.json'),levels=[a,b],input_sha256=src['assignment_sha256']))
        checked,two=other(dict(task,kind='secondary',gap=LEVELS[b],weight=25),cfg,checked[0],checked[1]['nonzero'],folder)
        record=dict(scope='two_stage',primary=one,secondary=two,seconds=one['seconds']+two['seconds'],
                    selected=[a,b],gate=one['gate'] and two['gate'])
    elif task['kind'] in ('cp','scip'):
        checked,record=primary(task,cfg,data,vals,folder,src['assignment_sha256'])
    else:
        if task['kind']=='secondary' and task.get('gap') is not None and not src['record']['gate']:
            raise ValueError('Cannot switch before global gap')
        checked,record=other(task,cfg,data,vals,folder)
    elapsed=time.monotonic()-started
    sched,assignment,physical,replay,rows=checked
    save(folder/'assignment.json.gz',assignment)
    save(folder/'schedule.json',sched)
    if task.get('figure'):
        from gantt import draw
        save(folder/'figure.json',draw(sched,folder/'figures'))
    budget=task.get('seconds')
    eligible=budget is None or record['seconds']<=budget+spec['fixed_budget_tolerance_s']
    if 'budget_eligible' in src: eligible=eligible and src['budget_eligible']
    save(folder/'evidence.json',dict(valid=True,cell=task_key,case=task['case'],input=task['start'],tables=task['tables'],
         source_sha256=src['schedule_sha256'],input_sha256=src['assignment_sha256'],initial=physical_metrics(data),
         metrics=physical,record=record,replay=replay,original_rows=rows,wall_s=elapsed,budget_s=budget,
         budget_eligible=eligible,worker_sha256=sha(Path(__file__)),schedule_sha256=sha(folder/'schedule.json'),
         assignment_sha256=sha(folder/'assignment.json.gz'),peak_rss_mib=psutil.Process().memory_info().peak_wset/2**20))
    print(task_key,physical['cmax'],physical['secondary'],record.get('gap'),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('cell')
    args=p.parse_args()
    run(args.cell)
