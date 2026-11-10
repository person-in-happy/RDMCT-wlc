"""Isolated CIE follow-up experiments on the authoritative JMS D model.

No fixed SCIP or process memory quota. Foreground orchestration, serialized GPU
use, immutable protocols, end-to-end wall accounting, retained failure records.
plan/prepare/check do not call optimize; start/resume are explicit execution.
"""
from pathlib import Path
from dataclasses import asdict, replace
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT/'JMS-version/model4_pjob_nonprocessing_20261103'
BASE = ROOT/'cie/results/current_jms'
ARMS = {
    'cold_scip': ('none','scip'), 'cold_hem': ('none','hem'),
    'cold_proposed': ('none','proposed'), 'serial_scip': ('serial','scip'),
    'spbs_scip': ('spbs','scip'), 'spbs_hem': ('spbs','hem'),
    'spbs_proposed': ('spbs','proposed'),
}

def read(p): return json.loads(Path(p).read_text('utf-8-sig'))
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,d):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    tmp.replace(p)
def utc(): return datetime.now(timezone.utc).isoformat()
def finite(v):
    if isinstance(v,float) and not math.isfinite(v): return None
    if isinstance(v,dict): return {k:finite(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)): return [finite(x) for x in v]
    return v

def backend():
    sys.path.insert(0,str(BACKEND))
    import model, run_experiments, seed, reference_completion, joint_algorithms, validate
    for module in (model,run_experiments,seed,reference_completion,joint_algorithms,validate):
        if Path(module.__file__).resolve().parent != BACKEND:
            raise RuntimeError('Wrong model import: '+str(module.__file__))
    return model,run_experiments,seed,reference_completion,joint_algorithms,validate

def case_plan(suite):
    # Inputs are selected by factors, never by observed feasibility or improvement.
    rows=[]
    if suite=='pilot':
        factors=[(2,2,3,8,(2,3)),(2,1,3,8,(2,3)),
                 (4,2,10,8,(2,3)),(4,2,2,4,(2,))]
    elif suite=='generalization':
        # Exactly match the new JMS qualification design, without requiring an
        # incumbent and without charging an external qualification solve.
        for n in (2,4,8):
            for recipe in ('4x1','2x2','mixed'):
                for scenario,(layout,h,d) in enumerate((('concentrated',2,4),('spread',3,6),('skew',5,8)),1):
                    ports={f'LP{i}':{'4x1':0,'2x2':0} for i in range(1,5)}
                    for j in range(n):
                        mode=recipe if recipe!='mixed' else ('4x1' if j<n//2 else '2x2')
                        lp=1 if layout=='concentrated' else j%4+1 if layout=='spread' else (1 if j<(n+1)//2 else 2)
                        ports[f'LP{lp}'][mode]+=1
                    rows.append(dict(case=f'n{n}_{recipe}_scenario{scenario}',load_ports=ports,
                        cleaning_interval=h,dummy_count=d,chambers=[2,3],n=n,
                        nfull=sum(p['4x1'] for p in ports.values())))
        return rows
    elif suite=='coupling':
        factors=[(n,f,2,d,ch) for n,f in ((4,2),(6,3),(6,0),(12,12))
                 for d in (4,8) for ch in ((2,),(2,3))]
    elif suite=='modes':
        factors=[(n,f,h,8,(2,3)) for n in (4,8,12) for h in (2,10)
                 for f in (0,n//2,n)]
    else: raise ValueError(suite)
    for n,nfull,h,d,ch in factors:
        ports={f'LP{i}':{'4x1':0,'2x2':0} for i in range(1,5)}
        for j in range(n): ports[f'LP{j%4+1}']['4x1' if j<nfull else '2x2']+=1
        case=f'n{n}_f{nfull}_H{h}_a{d}_ch'+''.join(map(str,ch))
        rows.append(dict(case=case,load_ports=ports,cleaning_interval=h,
                         dummy_count=d,chambers=list(ch),n=n,nfull=nfull))
    return rows

def safe_campaign(value):
    p=Path(value).resolve()
    if p==BASE or not p.is_relative_to(BASE): raise ValueError('Use a new subdirectory of cie/results/current_jms')
    return p

def assets():
    _,r,_,_,_,_=backend()
    return r.assets()|{str(Path(__file__).relative_to(ROOT)):digest(__file__)}

def environment():
    from importlib.metadata import version
    import platform,psutil
    return dict(python=sys.executable,python_version=sys.version,platform=platform.platform(),
                cpu=platform.processor(),logical_cpus=psutil.cpu_count(),ram_bytes=psutil.virtual_memory().total,
                packages={k:version(k) for k in ('pyscipopt','torch','numpy','psutil')})

def prepare(a,out):
    if out.exists(): raise FileExistsError('Existing campaign stays immutable; choose a new name')
    model,_,_,_,alg,_=backend()
    if len(set(a.seeds))!=len(a.seeds) or len(set(a.training_seeds))!=len(a.training_seeds):
        raise ValueError('Seeds must be distinct')
    if not 0<a.init_fraction<.5 or not 0<a.min_available_fraction<.5 or a.budget<=0:
        raise ValueError('Invalid budget or fractions')
    if a.wall_grace<0 or a.wall_grace>5: raise ValueError('Wall grace must be between 0 and 5 s')
    cases=case_plan(a.suite);cells=[];configs={};policies={}
    for c in cases:
        cfg=asdict(model.Config(**{k:v for k,v in c.items() if k not in ('case','n','nfull')}))
        assert cfg['max_pairs']==cfg['max_cycles']==0
        assert (cfg['module_residency'],cfg['robot_residency'],cfg['horizon'])==(100,100,10000)
        configs[c['case']]=cfg
        for arm in a.arms:
            init,method=ARMS[arm]
            for train in ([1] if method=='scip' else a.training_seeds):
                record=alg.policy_record(method,train)
                policies[f'{method}:{train}']=record
                for seed in a.seeds:
                    cells.append(dict(id=f'{c["case"]}__{arm}__s{seed}__t{train}',
                        case=c['case'],arm=arm,initialization=init,method=method,
                        seed=seed,training_seed=train))
    spec=dict(schema=1,created_utc=utc(),suite=a.suite,configs=configs,cells=cells,
        settings=dict(budget=a.budget,init_fraction=a.init_fraction,wall_grace=a.wall_grace,
            min_available_fraction=a.min_available_fraction,threads=1,jobs=1,
            memory_policy='native_unlimited_with_system_available_fraction_guard',
            cut_profile='standard',stage2=False,cleanup=False),
        assets=assets(),policies=policies,environment=environment(),
        interpretation='Frozen CIE policies transferred to JMS D; solver seeds and training seeds are not new instances.',
        budget_scope='From cell launch through imports, construction, model building, mapping, policy loading, search and checkpoint validation/serialization. Independent final audit is separately timed.',
        mode_scope='Equal nominal per-wafer processing duration; alternative recipe allocations, not proof that product recipes are interchangeable.',
        failure_policy='Initialization failure or timeout falls back to a cold main solve with remaining wall budget. No failed rows discarded. Late outputs excluded from budget-qualified results.')
    out.mkdir(parents=True)
    for case,cfg in configs.items(): dump(out/'configs'/f'{case}.json',cfg)
    spec['config_hashes']={c:digest(out/'configs'/f'{c}.json') for c in configs}
    dump(out/'campaign.json',spec);dump(out/'contract.json',dict(sha256=digest(out/'campaign.json')))
    for rel in spec['assets']:
        target=out/'frozen_code'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,target)
    print(json.dumps(dict(prepared=str(out),cases=len(configs),cells=len(cells),solver_started=False)),flush=True)

def checked(out):
    spec=read(out/'campaign.json')
    if digest(out/'campaign.json')!=read(out/'contract.json')['sha256']: raise RuntimeError('Protocol changed')
    if spec['assets']!=assets() or spec['environment']!=environment(): raise RuntimeError('Code/environment changed; create a new campaign')
    for case,h in spec['config_hashes'].items():
        if digest(out/'configs'/f'{case}.json')!=h: raise RuntimeError('Config changed')
    alg=backend()[4]
    for k,expected in spec['policies'].items():
        method,t=k.split(':')
        if alg.policy_record(method,int(t))!=expected: raise RuntimeError('Policy changed')
    return spec

def checkpoint_files(dest,deadline):
    # Atomic checkpoint JSON embeds the full assignment and validation evidence.
    good=[]
    for p in dest.glob('checkpoint_*.json'):
        d=read(p)
        if p.stat().st_mtime<=deadline and d['validated_epoch']<=deadline and d.get('valid'):
            good.append((d['cmax'],d['validated_epoch'],p))
    return sorted(good,key=lambda x:(x[0],x[1]))

def phase(a):
    # Parent has already frozen and checked protocol. Imports consume wall budget.
    out=safe_campaign(a.campaign);spec=read(out/'campaign.json')
    cell=next(c for c in spec['cells'] if c['id']==a.cell)
    dest=out/'runs'/cell['id']/a.phase;dest.mkdir(parents=True,exist_ok=False)
    started=time.time();model,r,seed,completion,alg,validator=backend()
    from scip_imports import scip
    cfg=model.Config(**spec['configs'][cell['case']]);x=None
    info=dict(phase=a.phase,started_epoch=started,deadline_epoch=a.deadline,cell=cell)
    try:
        x=model.Integrated(cfg);m=x.model
        if m.getParam('limits/memory')<1e12: raise RuntimeError('Unexpected fixed SCIP memory quota')
        m.setIntParam('parallel/maxnthreads',1);m.setIntParam('randomization/randomseedshift',cell['seed'])
        m.setLogfile(str(dest/'solver.log'))
        info['model_build_wall']=time.time()-started
        info['dimensions']=dict(variables=m.getNVars(),constraints=m.getNConss())
        count=0;best_seen=math.inf
        def save(sol,origin):
            nonlocal count,best_seen
            if time.time()>=a.deadline:return
            cmax=float(m.getSolVal(sol,x.cmax))
            if cmax>=best_seen-1e-7:return
            # Eligibility requires full original-model feasibility plus physical replay.
            if not m.checkSol(sol,printreason=False,completely=True,original=True):return
            result=x.result(solution=sol);verdict=validator.validate(result)
            if not verdict['valid']:return
            values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
            now=time.time()
            if now>=a.deadline:return
            count+=1
            data=finite(dict(valid=True,cmax=cmax,validated_epoch=now,origin=origin,
                values=values,result=result,validation=verdict,
                bound=None,
                bound_scope='full_primary' if a.phase=='main' else 'restricted_initialization'))
            dump(dest/f'checkpoint_{count:05d}.json',data)
            best_seen=cmax
            print(f'CHECKPOINT {origin} Cmax={cmax:.6f} elapsed={time.time()-started:.2f}s',flush=True)

        if a.phase=='init':
            before=time.time()
            schedule=seed.construct(cfg);dump(dest/'constructed_schedule.json',schedule)
            info['construction_wall']=time.time()-before
            # Completion runs on a private active submodel; parent enforces the
            # initialization wall slice even if its internal SCIP call overruns.
            # Bind only this private child process; frozen backend files remain
            # untouched. Completion must use the same solver seed and one thread.
            def single_thread_model(config):
                sub=model.Integrated(config)
                sub.model.setIntParam('parallel/maxnthreads',1)
                sub.model.setIntParam('randomization/randomseedshift',cell['seed'])
                return sub
            completion.Integrated=single_thread_model
            _,values,_,detail=completion.complete_reference(x,schedule,m.getParam('limits/memory'),0)
            info['reference_completion']=detail
            sol=m.createSol()
            for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
            save(sol,'serial');m.freeSol(sol)
            if cell['initialization']=='spbs' and time.time()<a.deadline:
                values,levels=alg.improve_skeleton(x,values,max(0,a.deadline-time.time()-.1))
                dump(dest/'spbs_levels.json',levels)
                sol=m.createSol()
                for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
                save(sol,'spbs');m.freeSol(sol)
        else:
            if a.warm:
                data=read(a.warm);sol=m.createSol()
                for v in m.getVars(transformed=False):m.setSolVal(sol,v,data['values'][v.name])
                if not m.checkSol(sol,printreason=False,completely=True,original=True):
                    m.freeSol(sol);raise RuntimeError('Saved initialization rejected by full model')
                save(sol,'initialization');m.addSol(sol)
            load=time.time();agent,policy=alg.install(m,cell['method'],cell['training_seed'])
            info['policy_load_wall']=time.time()-load;info['policy']=policy
            class Trace(scip.Eventhdlr):
                def eventinit(self): self.model.catchEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND,self)
                def eventexit(self): self.model.dropEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND,self)
                def eventexec(self,event):
                    sol=self.model.getBestSol()
                    if sol is not None:save(sol,'primary')
                    if time.time()>=a.deadline:self.model.interruptSolve()
            m.includeEventhdlr(Trace(),'cie_budget_trace','Validated full assignments during wall-bounded solve')
            remaining=a.deadline-time.time()
            if remaining>0:
                m.setRealParam('limits/time',remaining);m.optimize()
                if m.getNSols():save(m.getBestSol(),'final')
            info.update(status=str(m.getStatus()),solver_seconds=m.getSolvingTime(),
                dual_bound=float(m.getDualbound()),bound_scope='full_primary',
                finished_within_budget=time.time()<=a.deadline)
            if agent is not None:dump(dest/'cutsel_telemetry.json',agent.get_telemetry())
        info['ended_epoch']=time.time();dump(dest/'phase.json',finite(info))
    except Exception as exc:
        info.update(error=repr(exc),ended_epoch=time.time());dump(dest/'error.json',finite(info))
        raise
    finally:
        if x is not None:x.model.freeProb()

def terminate_tree(proc):
    import psutil
    try: children=psutil.Process(proc.pid).children(recursive=True)
    except psutil.Error: children=[]
    for p in reversed(children):
        try:p.terminate()
        except psutil.Error:pass
    if proc.poll() is None:proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()

def execute_phase(out,cell,stage,deadline,grace,min_available,warm=None,progress=None):
    import psutil
    cmd=[sys.executable,'-X','utf8','-u',str(Path(__file__).resolve()),'_phase',
         '--campaign',str(out),'--cell',cell['id'],'--phase',stage,'--deadline',str(deadline)]
    if warm:cmd+=['--warm',str(warm)]
    log=out/'runs'/cell['id']/(stage+'.console.log');began=time.time();reason=None
    minimum=1.;peak=0;last=0
    with log.open('wb') as f:
        proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
        try:
            while proc.poll() is None:
                now=time.time();vm=psutil.virtual_memory();fraction=vm.available/vm.total;minimum=min(minimum,fraction)
                try:
                    pp=psutil.Process(proc.pid)
                    peak=max(peak,sum(p.memory_info().rss for p in [pp]+pp.children(recursive=True)))
                except psutil.Error:pass
                if fraction<min_available:reason='system_available_memory_guard'
                elif now>=deadline+grace:reason='wall_budget_reached'
                if reason:terminate_tree(proc);break
                if now-last>=10:
                    print(f'{progress or ""} {cell["id"]} {stage} remaining={max(0,deadline-now):.1f}s RAMfree={fraction:.1%}',flush=True);last=now
                time.sleep(.1)
        except BaseException:
            terminate_tree(proc);raise
    return dict(phase=stage,exit_code=proc.returncode,reason=reason,wall_seconds=time.time()-began,
                deadline_epoch=deadline,ended_epoch=time.time(),peak_rss_bytes=peak,
                minimum_available_fraction=minimum,log=str(log.relative_to(out)))

def coverage(out):
    spec=read(out/'campaign.json');counts=dict(expected=len(spec['cells']),complete=0,failed=0,pending=0,valid=0)
    for c in spec['cells']:
        dest=out/'runs'/c['id']
        if (dest/'execution.json').exists():
            e=read(dest/'execution.json');counts['complete']+=1
            counts['failed']+=int(e['execution_error']);counts['valid']+=int(e['qualified_incumbent'] is not None)
        else:counts['pending']+=1
    return counts

def run(out):
    import psutil
    from contextlib import ExitStack
    spec=checked(out)
    from run_matched_supplement import output_lock
    from paper_defaults import ensure_idle
    ensure_idle()
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid==os.getpid():continue
        if 'python' in (p.info['name'] or '').lower():
            cmd=p.info['cmdline'] or []
            if any(Path(t).name in ('run_current_jms_experiments.py','journal_support_experiments.py','journal_gap_experiments.py','thesis_gap_experiments.py','run_cie_benchmarks.py') for t in cmd) and any(t in ('start','resume','_phase','_worker','run') for t in cmd):
                raise RuntimeError(f'An experiment is active: PID {p.pid}')
    st=spec['settings'];durations=[]
    with ExitStack() as stack:
        BASE.mkdir(parents=True,exist_ok=True)
        stack.enter_context(output_lock(BASE/'.foreground_queue'))
        stack.enter_context(output_lock(out))
        for cell in spec['cells']:
            dest=out/'runs'/cell['id']
            if (dest/'execution.json').exists():continue
            if dest.exists():raise RuntimeError('Interrupted attempt preserved; inspect it and use a new campaign: '+str(dest))
            if psutil.virtual_memory().available/psutil.virtual_memory().total<st['min_available_fraction']:
                raise RuntimeError('Low system available memory; no new worker launched')
            dest.mkdir(parents=True);counts=coverage(out)
            eta=(sum(durations)/len(durations) if durations else st['budget'])*counts['pending']/3600
            progress=f'complete={counts["complete"]}/{counts["expected"]} failed={counts["failed"]} ETA~{eta:.2f}h'
            print('START '+progress+' '+cell['id'],flush=True)
            begin=time.time();deadline=begin+st['budget'];stages=[];warm=None
            try:
                if cell['initialization']!='none':
                    init_deadline=begin+st['budget']*st['init_fraction']
                    stages.append(execute_phase(out,cell,'init',init_deadline,st['wall_grace'],st['min_available_fraction'],progress=progress))
                    choices=checkpoint_files(dest/'init',init_deadline)
                    if choices:warm=choices[0][2]
                if time.time()<deadline and not any(s['reason']=='system_available_memory_guard' for s in stages):
                    stages.append(execute_phase(out,cell,'main',deadline,st['wall_grace'],st['min_available_fraction'],warm,progress))
            except KeyboardInterrupt:
                dump(dest/'interrupted.json',dict(ended_utc=utc(),stages=stages));raise
            allcp=checkpoint_files(dest/'main',deadline)
            if warm:allcp+=checkpoint_files(dest/'init',min(deadline,begin+st['budget']*st['init_fraction']))
            allcp.sort(key=lambda x:(x[0],x[1]));best=allcp[0][2] if allcp else None
            errors=any(s['exit_code']!=0 and s['reason']!='wall_budget_reached' for s in stages if s['phase']=='main')
            errors=errors or any(s['reason']=='system_available_memory_guard' for s in stages)
            finished=time.time()
            result=dict(cell=cell,started_epoch=begin,deadline_epoch=deadline,ended_epoch=finished,
                wall_seconds=finished-begin,wall_overshoot_seconds=max(0,finished-deadline),
                stages=stages,construction_fallback=cell['initialization']!='none' and warm is None,
                execution_error=errors,qualified_incumbent=str(best.relative_to(out)) if best else None,
                checkpoint_sha256=digest(best) if best else None,
                scientific_status='feasible_pending_independent_audit' if best else 'no_qualified_incumbent',
                cmax=read(best)['cmax'] if best else None,
                upper_bound_trajectory=[dict(elapsed=d[1]-begin,cmax=d[0],file=str(d[2].relative_to(out))) for d in sorted(allcp,key=lambda d:d[1])])
            dump(dest/'execution.json',result);durations.append(finished-begin)
            print('DONE '+json.dumps(coverage(out)),flush=True)
        dump(out/'finished.json',coverage(out))

def audit(out):
    spec=checked(out);model,_,_,_,_,validator=backend();rows=[];begin=time.time()
    for cell in spec['cells']:
        p=out/'runs'/cell['id'];ep=p/'execution.json'
        if not ep.exists():rows.append(dict(id=cell['id'],state='pending'));continue
        execution=read(ep);record=execution['qualified_incumbent'];valid=False;metrics={}
        if record:
            file=out/record
            if digest(file)!=execution['checkpoint_sha256']:raise RuntimeError('Checkpoint changed')
            d=read(file);x=model.Integrated(model.Config(**spec['configs'][cell['case']]));m=x.model
            try:
                sol=m.createSol()
                for v in m.getVars(transformed=False):m.setSolVal(sol,v,d['values'][v.name])
                original=bool(m.checkSol(sol,printreason=False,completely=True,original=True))
                replay=x.result(solution=sol);physical=validator.validate(replay);m.freeSol(sol)
                valid=original and physical['valid']
                metrics=dict(cmax=replay['cmax'],cleanings=sum(c['mode']=='clean' for c in replay['cycles']),
                    cycles=len(replay['cycles']),pair_count=len(replay['pairs']))
                dump(p/'audit_result.json',finite(dict(valid=valid,original_model_check=original,physical=physical,result=replay)))
                if not valid:raise RuntimeError('Independent validation failed: '+cell['id'])
            finally:m.freeProb()
        rows.append(dict(cell=cell,state=execution['scientific_status'],valid=valid,
                         execution_error=execution['execution_error'],metrics=metrics,
                         construction_fallback=execution['construction_fallback'],wall_seconds=execution['wall_seconds'],
                         wall_overshoot_seconds=execution['wall_overshoot_seconds']))
        print(f'AUDIT {len(rows)}/{len(spec["cells"])} valid={sum(r.get("valid",False) for r in rows)}',flush=True)
    report=dict(rows=rows,coverage=coverage(out),audit_wall_seconds=time.time()-begin,solver_started=False,
                note='No solve-only PDI ranking. No significance or global-optimality claim inferred from this audit.')
    dump(out/'analysis/audit.json',finite(report));print(json.dumps(report['coverage']))

def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('action',choices=['plan','prepare','check','start','resume','status','audit','_phase'])
    p.add_argument('--campaign');p.add_argument('--suite',choices=['pilot','generalization','coupling','modes'],default='pilot')
    p.add_argument('--arms',nargs='+',choices=ARMS,default=list(ARMS))
    p.add_argument('--seeds',type=int,nargs='+',default=[1,2,3]);p.add_argument('--training-seeds',type=int,nargs='+',default=[1])
    p.add_argument('--budget',type=float,default=600);p.add_argument('--init-fraction',type=float,default=.2)
    p.add_argument('--min-available-fraction',type=float,default=.1);p.add_argument('--wall-grace',type=float,default=.5)
    p.add_argument('--cell',help=argparse.SUPPRESS);p.add_argument('--phase',choices=['init','main'],help=argparse.SUPPRESS)
    p.add_argument('--deadline',type=float,help=argparse.SUPPRESS);p.add_argument('--warm',help=argparse.SUPPRESS)
    a=p.parse_args()
    if a.action=='plan':
        cases=case_plan(a.suite)
        n=len(cases)*len(a.seeds)*sum(1 if ARMS[arm][1]=='scip' else len(a.training_seeds) for arm in a.arms)
        print(json.dumps(dict(suite=a.suite,cases=cases,arms=a.arms,cells=n,nominal_serial_hours=n*a.budget/3600,solver_started=False),ensure_ascii=False,indent=2));return
    if not a.campaign:p.error('--campaign is required')
    out=safe_campaign(a.campaign)
    if a.action=='prepare':prepare(a,out)
    elif a.action=='check':
        s=checked(out);print(json.dumps(dict(cells=len(s['cells']),solver_started=False,backend=str(BACKEND))))
    elif a.action in ('start','resume'):run(out)
    elif a.action=='status':print(json.dumps(coverage(out)))
    elif a.action=='audit':audit(out)
    else:phase(a)

if __name__=='__main__':main()
