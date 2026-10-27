"""Isolated, serial, resumable evidence campaigns for optional early cleaning.

Main optimization budgets exclude model building and shared offline starts.
Completed timeouts without incumbents remain completed observations, not proofs.
"""
from pathlib import Path
from dataclasses import asdict,replace
from datetime import datetime,timezone
import argparse,copy,csv,hashlib,json,math,os,statistics,subprocess,sys,time,traceback
from model import Config,Integrated,ROOT
from seed import construct,constrain_seed,release_fixed
from validate import validate
from supplement_protocol import balanced_reference
from run_experiments import assets,digest,dump,finite,ports,solve
from joint_algorithms import policy_record,improve_skeleton
from run_matched_supplement import output_lock

HERE=Path(__file__).resolve().parent
VARIANTS={
    'joint':dict(method='scip'),
    'fixed':dict(method='scip',fixed=True),
    'legacy':dict(method='scip',cleaning_rule='legacy'),
    'refined':dict(method='scip',refine=True),
    'hem':dict(method='hem'),
    'proposed':dict(method='proposed'),
    'cold':dict(method='scip',warm=None),
    'serial':dict(method='scip',warm='serial'),
    'partition':dict(method='scip',fixed=True,partition=True),
    'feature_only':dict(method='feature_only'),
    'greedy':dict(method='proposed_greedy'),
    'no_structure':dict(method='proposed_no_structure'),
    'waiting_only':dict(method='scip',refine=True,refinement_objective='waiting_only'),
    'quadratic':dict(method='scip',refine=True,refinement_objective='quadratic'),
}

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def stamp():return datetime.now(timezone.utc).isoformat()
def inventory():
    return assets()|{str(p.relative_to(ROOT)):digest(p) for p in
        (Path(__file__),HERE/'supplement_protocol.py',HERE/'run_matched_supplement.py')}

def plan(suite):
    """Explicit input matrix; repeated solver seeds are not independent instances."""
    cases={};cells=[]
    def add(n,h,source='dual',recipe='mixed',variants=('joint',),tag='',**overrides):
        key=f'n{n}_H{h}_{recipe}_{source}'+('_'+tag if tag else '')
        cfg=asdict(replace(Config(ports(n,recipe),source=source,cleaning_interval=h),**overrides))
        if key in cases:assert cases[key]==cfg
        cases[key]=cfg
        for variant in variants:
            if (key,variant) not in cells:cells.append((key,variant))
    arms=('joint','fixed','legacy','refined','hem','proposed','cold','serial')
    if suite=='core':
        for n,h,source in ((4,3,'dual'),(4,3,'single'),(4,10,'dual'),(8,3,'dual')):
            add(n,h,source,variants=arms)
        for n in (4,8):
            for h in (3,10):
                for recipe in ('4x1','2x2','mixed'):add(n,h,recipe=recipe)
        add(4,10,variants=('partition',))
    elif suite=='smoke':
        add(1,3,recipe='4x1',variants=('joint','refined','legacy','hem','proposed'))
    elif suite=='crossover':
        for n in (8,16,24):
            for h in range(3,11):
                for recipe in ('4x1','2x2','mixed'):add(n,h,recipe=recipe)
    elif suite=='ablation':
        for n in (4,8):
            for h in (3,10):
                for source in ('single','dual'):
                    add(n,h,source,variants=('joint','hem','proposed','feature_only','greedy','no_structure','refined','waiting_only','quadratic'))
    elif suite=='sensitivity':
        for n in (4,8):
            for source in ('single','dual'):
                add(n,3,source)
                for factor in (.9,1.1):add(n,3,source,tag=f'process{factor}',full_time=180*factor,mix_time=90*factor)
                for d in (4,6,10):add(n,3,source,tag=f'dummy{d}',dummy_count=d)
                for factor in (.8,1.2):add(n,3,source,tag=f'transport{factor}',handling=factor,atr_handling=4*factor,vtr_travel=2*factor,atr_travel=3*factor)
    elif suite=='doe':
        for n in (8,16,24,32):
            for fraction in (0,.25,.5,.75,1):
                lp={f'LP{i}':{'4x1':0,'2x2':0} for i in range(1,5)}
                for j in range(n):lp[f'LP{j%4+1}']['4x1' if j<int(n*fraction) else '2x2']+=1
                for factor in (.9,1,1.1):
                    add(n,3,tag=f'fullshare{fraction}_process{factor}',load_ports=lp,full_time=180*factor,mix_time=90*factor)
    elif suite in ('scale','ood'):
        for n in ((8,16,24,32) if suite=='scale' else (40,48,64)):
            for recipe in ('4x1','2x2','mixed'):add(n,3,recipe=recipe,variants=('joint','hem','proposed') if suite=='ood' else ('joint',))
    else:raise ValueError(suite)
    return cases,cells

def prepare(args):
    cases,pairs=plan(args.suite)
    selected=getattr(args,'cases',None)
    if selected is not None:
        unknown=set(selected)-set(cases)
        if unknown:raise ValueError('Unknown cases: '+', '.join(sorted(unknown)))
        cases={key:cfg for key,cfg in cases.items() if key in selected}
        pairs=[(key,variant) for key,variant in pairs if key in cases]
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'configs').mkdir();cells=[]
    for key,cfg in cases.items():dump(out/'configs'/f'{key}.json',cfg)
    # Traverse paired methods within each seed, so partial progress remains useful.
    for seed in args.seeds:
        for key,variant in pairs:
            cells.append(dict(id=f'{key}__s{seed}__{variant}',case=key,variant=variant,seed=seed))
    methods=sorted({VARIANTS[v]['method'] for _,v in pairs})
    protocol=dict(schema=1,suite=args.suite,created_utc=stamp(),assets=inventory(),
        policies={m:policy_record(m,args.training_seed) for m in methods},training_seed=args.training_seed,
        time_limit=args.time_limit,seeds=args.seeds,spbs_budget=args.spbs_budget,
        cut_profile=args.cut_profile,memory_mb=args.memory_mb,wall_limit=args.wall_limit,
        case_hashes={k:digest(out/'configs'/f'{k}.json') for k in cases},cells=cells,
        accounting='300s main solve, or 270s primary + 30s refinement; shared preparation and model build reported separately',
        scope='Frozen-policy transfer; no claim of retraining, industrial deployment, or global optimality from timeouts')
    if selected is not None:protocol['selected_cases']=list(cases)
    dump(out/'campaign.json',protocol)
    print(json.dumps(dict(campaign=str(out),cases=len(cases),runs=len(cells),main_budget_hours=len(cells)*args.time_limit/3600)))

def verify(out):
    if (out/'preparation_pending.json').exists():raise RuntimeError('Continuation preparation was interrupted; preserve this directory and use a new destination')
    spec=read(out/'campaign.json')
    if 'continuation_sha256' in spec:
        if digest(out/'continuation.json')!=spec['continuation_sha256']:raise RuntimeError('Continuation record changed')
        parent=read(out/'continuation.json')
        if digest(Path(parent['parent_audit']))!=parent['parent_audit_sha256']:raise RuntimeError('Parent evidence audit changed')
    if inventory()!=spec['assets']:raise RuntimeError('Code changed; create a new campaign. Frozen results retained.')
    for k,h in spec['case_hashes'].items():
        if digest(out/'configs'/f'{k}.json')!=h:raise RuntimeError('Configuration changed: '+k)
    for method,record in spec['policies'].items():
        if policy_record(method,spec['training_seed'])!=record:raise RuntimeError('Frozen policy changed')
    return spec

def certify(x,values):
    m=x.model;sol=m.createSol()
    for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
    valid=m.checkSol(sol,printreason=False,completely=True);m.freeSol(sol)
    if not valid:raise RuntimeError('Common start violates released full model')

def prepare_reference(out,key,spec,partition=False):
    directory=out/'references'/(key+('_partition' if partition else ''))
    if (directory/'certificate.json').exists():
        cert=read(directory/'certificate.json')
        for name,h in cert['files'].items():
            if digest(directory/name)!=h:raise RuntimeError('Common reference file changed')
        return directory
    if directory.exists():
        archive=out/'interrupted_attempts'/(directory.name+'_reference_'+str(time.time_ns()))
        archive.parent.mkdir(exist_ok=True);directory.rename(archive)
    directory.mkdir(parents=True)
    started=time.monotonic();cfg=Config(**read(out/'configs'/f'{key}.json'))
    if cfg.max_pairs or cfg.max_cycles:raise ValueError('Evidence campaigns require full candidate capacity')
    if partition:
        base=prepare_reference(out,key,spec);template=copy.deepcopy(read(base/'reference.json'));mapping={}
        for p in sorted(template['pairs'],key=lambda p:p['id']):
            for r,w in enumerate(p['members']):
                if w.startswith('D'):
                    identity=(p['chamber'],w)
                    if identity not in mapping:mapping[identity]=f'D{len(mapping)+1}'
                    p['members'][r]=mapping[identity]
        if len(mapping)>cfg.dummy_count:raise ValueError('Partition exceeds inventory')
        schedule=construct(cfg,template)
    else:schedule=balanced_reference(cfg)
    dump(directory/'serial_schedule.json',schedule)
    from reference_completion import complete_reference
    x=Integrated(cfg);m=x.model
    m.setRealParam('limits/memory',spec['memory_mb'])
    serial,values,levels,completion=complete_reference(x,schedule,spec['memory_mb'],0 if partition else spec['spbs_budget'])
    dump(directory/'serial.json',dict(values=serial));del serial
    dump(directory/'completion.json',completion)
    certify(x,values)
    # Recover the exact physical start corresponding to these complete variables.
    sol=m.createSol()
    for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
    # Export this exact assignment, avoiding a different tied incumbent.
    reference=x.result(solution=sol);m.freeSol(sol)
    if not validate(reference)['valid']:raise RuntimeError('Improved reference failed physical replay')
    dump(directory/'reference.json',reference);dump(directory/'common.json',dict(values=values))
    dump(directory/'spbs_levels.json',levels)
    cert=dict(valid=True,seconds=time.monotonic()-started,spbs_budget=spec['spbs_budget'],dimensions=x.original_dimensions,
        cmax=validate(reference)['product_return_cmax'],scope='partition' if partition else 'shared_offline_spbs',
        files={name:digest(directory/name) for name in ('reference.json','common.json','serial.json','serial_schedule.json','spbs_levels.json','completion.json')})
    dump(directory/'certificate.json',finite(cert));m.freeProb()
    return directory

def metrics(data):
    """Recompute waiting and rhythm from physical exported events."""
    if not data.get('solutions'):return {}
    cfg=data['config'];events={};waits=[]
    for e in data['events']:
        if 'job' in e:events.setdefault(e['job'],{})[e['kind']]=e
    for j in data['jobs']:
        es=events[j['name']]
        waits.extend((j['load_start']-es['source_pick']['end']-cfg['vtr_travel'],es['destination_put']['start']-j['unload_end']-cfg['vtr_travel']))
        if j['origin']!='VS':
            legs=[('origin_pick','al_put',cfg['atr_travel']),('al_put','al_pick',cfg['alignment']),('al_pick','upper_put',cfg['atr_travel'])] if 'al_put' in es else [('origin_pick','upper_put',cfg['atr_travel'])]
            legs += [('upper_put','source_pick',cfg['pump']),('destination_put','lower_pick',cfg['vent']),('lower_pick','origin_put',cfg['atr_travel'])]
            waits.extend(es[b]['start']-es[a]['end']-d for a,b,d in legs)
    if min(waits,default=0)<-2e-4:raise ValueError('Negative recomputed route wait')
    rhythm=[];intervals=[];early=0;legacy_ok=True
    for c in cfg['chambers']:
        cs=sorted((v for v in data['cycles'] if v['chamber']==c),key=lambda v:v['index']);count=0
        for i,cy in enumerate(cs):
            if cy['mode']=='clean':
                early+=count<cfg['cleaning_interval']
                legacy_ok &= count==cfg['cleaning_interval'] or (count==cfg['cleaning_interval']-1 and i+1<len(cs) and cs[i+1]['mode']=='2x2')
                count=0
            else:count+=1
            if i>=2:
                a,b,d=cs[i-2:i+1]
                if all(v['mode']=='2x2' for v in (a,b,d)) and set(a['pairs'])&set(b['pairs']) and set(b['pairs'])&set(d['pairs']):
                    rhythm.append(abs(d['start']-2*b['start']+a['start']))
                    intervals.extend((b['start']-a['start'],d['start']-b['start']))
    production=[c for c in data['cycles'] if c['mode']!='clean']
    overlap=sum(max(0,min(a['end'],b['end'])-max(a['start'],b['start']))
        for i,a in enumerate(production) for b in production[i+1:] if a['chamber']!=b['chamber'])
    return dict(route_wait_sum=sum(max(0,w) for w in waits),route_wait_max=max(waits,default=0),
        rhythm_deviation=sum(rhythm),rhythm_centers=len(rhythm),early_cleanings=early,legacy_rule_feasible=bool(legacy_ok),production_overlap=overlap)

def worker(out,cell_id):
    spec=verify(out);cell=next(c for c in spec['cells'] if c['id']==cell_id);arm=VARIANTS[cell['variant']]
    key=cell['case'];ref=prepare_reference(out,key,spec,arm.get('partition',False))
    warm=arm.get('warm','common');budget=spec['time_limit'];stage2=budget*.1 if arm.get('refine') else 0
    dest=out/'runs'/cell_id;dest.parent.mkdir(exist_ok=True)
    solve(out/'configs'/f'{key}.json',dest,time_limit=budget-stage2,stage2_limit=stage2,seed=cell['seed'],
        warm_start=ref/(warm+'.json') if warm else None,fixed=ref/'reference.json' if arm.get('fixed') else None,
        method=arm['method'],training_seed=spec['training_seed'],initialization='none',initialization_budget=0,
        memory_mb=spec['memory_mb'],cleaning_rule=arm.get('cleaning_rule','optional'),cut_profile=spec['cut_profile'],
        refinement_objective=arm.get('refinement_objective','full'))
    result=read(dest/'result.json');physical=validate(result);derived=metrics(result)
    if result.get('solutions') and (not physical['valid'] or not result.get('original_model_check')):
        raise RuntimeError('Incumbent failed original constraints or independent replay')
    if arm.get('cleaning_rule')=='legacy' and result.get('solutions') and not derived['legacy_rule_feasible']:
        raise RuntimeError('Legacy trigger replay failed')
    if warm and not read(dest/'warm_start_check.json')['accepted']:raise RuntimeError('Common warm start rejected')
    phase1=read(dest/'phase1.json');initial=read(ref/('serial_schedule.json' if warm=='serial' else 'reference.json'))
    structure=lambda r:sorted((p['id'],tuple(p['members']),p['chamber'],p['mode']) for p in r['pairs'])+[(c['chamber'],c['index'],c['mode'],tuple(c['pairs']),c['front']) for c in r['cycles']]
    cert=dict(complete=True,physical=physical,original_model_check=result.get('original_model_check',False),metrics=derived,
        phase1_metrics=metrics(phase1),common_reference_sha256=digest(ref/'reference.json'),
        common_warm_sha256=digest(ref/(warm+'.json')) if warm else None,offline_initialization=read(ref/'certificate.json'),
        initial_cmax=validate(initial)['product_return_cmax'],structure_changed=bool(result.get('solutions') and structure(result)!=structure(initial)),
        status=phase1['status'],solutions=result['solutions'],completed_utc=stamp(),result_sha256=digest(dest/'result.json'))
    dump(dest/'evidence.json',finite(cert))

def summarize(out):
    spec=read(out/'campaign.json');rows=[]
    for c in spec['cells']:
        dest=out/'runs'/c['id'];row=c|dict(state='pending')
        if (dest/'evidence.json').exists():
            cert=read(dest/'evidence.json');r=read(dest/'result.json');phase1=read(dest/'phase1.json')
            checked=validate(r)
            if digest(dest/'result.json')!=cert['result_sha256']:raise RuntimeError('Result changed: '+c['id'])
            has=bool(r.get('solutions'));valid=bool(checked['valid'] and cert['original_model_check'])
            state='optimal' if valid and cert['status']=='optimal' else 'feasible_limit' if valid else 'proven_infeasible' if cert['status']=='infeasible' else 'no_incumbent_'+cert['status']
            row.update(state=state,valid=valid,upper=checked.get('product_return_cmax') if valid else None,
                lower=r.get('primary_bound'),gap=r.get('primary_gap'),pdi=r.get('primary_primal_dual_integral'),
                full_candidate_space=r.get('full_candidate_space'),phase1_seconds=phase1['solve_seconds'],
                offline_seconds=cert['offline_initialization']['seconds'],structure_changed=cert['structure_changed'],**cert['metrics'])
            if (dest/'cutsel_telemetry.json').exists():
                t=read(dest/'cutsel_telemetry.json');row.update(cut_calls=t['callback_calls'],cut_callback_seconds=t['callback_time_seconds'])
            if not valid:row['upper']=None
        elif (dest/'failure.json').exists():row.update(state='execution_failed',reason=read(dest/'failure.json')['reason'])
        rows.append(row)
    folder=out/'summary';folder.mkdir(exist_ok=True);dump(folder/'cells.json',rows)
    with (folder/'cells.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in rows))));writer.writeheader();writer.writerows(rows)
    counts={s:sum(r['state']==s for r in rows) for s in sorted({r['state'] for r in rows})}
    comparisons=[]
    by={(r['case'],r['seed'],r['variant']):r for r in rows}
    for case,seed,variant in by:
        if variant!='joint':continue
        base=by[case,seed,variant]
        for other in ('legacy','fixed','hem','proposed','cold','serial','refined'):
            r=by.get((case,seed,other))
            if not r or not base.get('valid') or not r.get('valid'):continue
            comparison=dict(case=case,seed=seed,arm=other,joint_cmax=base['upper'],arm_cmax=r['upper'],
                arm_minus_joint_cmax=r['upper']-base['upper'],
                arm_minus_joint_pdi=r['pdi']-base['pdi'] if r.get('pdi') is not None and base.get('pdi') is not None and other!='refined' else None)
            if other in ('legacy','fixed'):
                comparison['joint_strictly_better_certified']=r.get('lower') is not None and base['upper']<r['lower']-2e-4
            if other in ('hem','proposed'):comparison['cut_calls']=r.get('cut_calls',0)
            if other=='refined':
                comparison.update(wait_sum_reduction=base['route_wait_sum']-r['route_wait_sum'],
                    rhythm_reduction=base['rhythm_deviation']-r['rhythm_deviation'],rhythm_centers=r['rhythm_centers'])
            comparisons.append(comparison)
    dump(folder/'paired_comparisons.json',comparisons)
    report=dict(expected=len(rows),states=counts,complete_observations=sum(r['state'] not in ('pending','execution_failed') for r in rows),
        paired_evidence='Compare identical case and seed; aggregate seeds within case before any instance-level inference.',
        claims='No automatic claim of significance, algorithm superiority or mode optimality. Inspect bounds and cut-call counts.')
    dump(folder/'coverage.json',report);print(json.dumps(report),flush=True);return report

def run(args):
    out=Path(args.campaign).resolve()
    with output_lock(out):
        spec=verify(out);progress=read(out/'progress.json') if (out/'progress.json').exists() else {'cells':{}}
        try:
            for cell in spec['cells']:
                cid=cell['id'];dest=out/'runs'/cid
                if (dest/'evidence.json').exists():continue
                if (dest/'failure.json').exists() and not args.retry_failed:continue
                verify(out)
                if dest.exists():
                    root=out.resolve();resolved=dest.resolve()
                    if not resolved.is_relative_to(root) or dest.is_symlink():raise RuntimeError('Unsafe output path')
                    archive=out/'interrupted_attempts'/(cid+'_'+str(time.time_ns()));archive.parent.mkdir(exist_ok=True);dest.rename(archive)
                progress['cells'][cid]=dict(state='running',started_utc=stamp());dump(out/'progress.json',progress)
                print('START '+cid,flush=True);logs=out/'logs';logs.mkdir(exist_ok=True)
                with (logs/(cid+'_'+str(time.time_ns())+'.log')).open('wb') as log:
                    child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'worker','--campaign',str(out),'--cell',cid],stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
                    started=time.monotonic();reason=None
                    # Limit build/serialization too; SCIP's memory cap starts only after construction.
                    import psutil
                    while child.poll() is None:
                        try:working_mb=psutil.Process(child.pid).memory_info().rss/1024**2
                        except psutil.NoSuchProcess:working_mb=0
                        from memory_policy import process_limit
                        if working_mb>process_limit(spec):reason='process_memory_guard'
                        if time.monotonic()-started>spec['wall_limit']:reason='cell_wall_guard'
                        if reason:
                            child.terminate();child.wait(timeout=30);break
                        time.sleep(2)
                    code=child.wait()
                success=code==0 and (dest/'evidence.json').exists()
                if not success:
                    dest.mkdir(parents=True,exist_ok=True);dump(dest/'failure.json',dict(reason=reason or f'exit_{code}',ended_utc=stamp()))
                progress['cells'][cid].update(state='complete' if success else 'execution_failed',exit_code=code,ended_utc=stamp())
                dump(out/'progress.json',progress);summarize(out)
            coverage=summarize(out);dump(out/'finished.json',coverage|dict(ended_utc=stamp(),all_cells_successful='execution_failed' not in coverage['states'] and 'pending' not in coverage['states']))
        except BaseException:
            dump(out/'stopped.json',dict(ended_utc=stamp(),traceback=traceback.format_exc()));raise

def main():
    p=argparse.ArgumentParser(__doc__);sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--suite',choices=['smoke','core','crossover','ablation','sensitivity','scale','doe','ood'],required=True);prep.add_argument('--output',required=True)
    prep.add_argument('--cases',nargs='+',help='Prepare only these explicit case IDs; store the subset in the frozen manifest')
    prep.add_argument('--time-limit',type=float,default=300);prep.add_argument('--seeds',type=int,nargs='+',default=[1,2,3]);prep.add_argument('--training-seed',type=int,default=1)
    prep.add_argument('--spbs-budget',type=float,default=20);prep.add_argument('--cut-profile',choices=['root_only','standard'],default='root_only');prep.add_argument('--memory-mb',type=float,default=14000);prep.add_argument('--wall-limit',type=float,default=1800)
    for cmd in ('run','summarize','worker'):
        parser=sub.add_parser(cmd);parser.add_argument('--campaign',required=True)
        if cmd=='run':parser.add_argument('--retry-failed',action='store_true')
        if cmd=='worker':parser.add_argument('--cell',required=True)
    a=p.parse_args()
    if a.command=='prepare':
        if a.time_limit<=0 or a.spbs_budget<0 or a.memory_mb<=0 or a.wall_limit<=a.time_limit:raise ValueError('Invalid budget')
        prepare(a)
    elif a.command=='run':run(a)
    elif a.command=='worker':worker(Path(a.campaign).resolve(),a.cell)
    else:summarize(Path(a.campaign).resolve())

if __name__=='__main__':main()
