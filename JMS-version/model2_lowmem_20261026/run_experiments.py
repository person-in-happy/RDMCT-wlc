"""Frozen, resumable experiments for the joint event model (seconds throughout)."""
from pathlib import Path
import argparse,hashlib,json,time,sys,platform,traceback
from dataclasses import asdict
from model import Config,Integrated,ROOT
from validate import validate
from seed import construct,constrain_seed,release_fixed
from joint_algorithms import install,policy_record,improve_skeleton

HERE=Path(__file__).resolve().parent

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()
def dump(p,data):
    p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(p)
def assets():
    paths=[HERE/n for n in ('model.py','validate.py','grippers.py','seed.py','run_experiments.py','joint_algorithms.py','joint_pairing_model.py','joint_chamber_cycle_model.py','reference_completion.py')]+[ROOT/n for n in ('scip_imports.py','runtime_compat.py','utils.py','cutsel_agent_parallel.py','environments.py','global_const.py')]+[ROOT/'cie/code/run_cie_benchmarks.py']
    paths += [HERE/'memory_policy.py',HERE/'low_memory_evidence.py']
    return {str(p.relative_to(ROOT)):digest(p) for p in sorted(paths)}
def finite(data):
    import math
    if isinstance(data,float) and not math.isfinite(data):return None
    if isinstance(data,dict):return {k:finite(v) for k,v in data.items()}
    if isinstance(data,(list,tuple)):return [finite(v) for v in data]
    return data

def incumbent_checks(model):
    """Check the original stage model, not final search-node domains.

SCIPcheckSol (the PySCIPOpt default) may reject a stored incumbent against
transformed variable bounds left by search. Keep that diagnostic separate;
feasibility acceptance uses SCIPcheckSolOrig and independent physical replay.
No feasibility tolerance or constraint is relaxed.
"""
    if not model.getNSols():
        return dict(original_model_check=False, transformed_model_check=False,
                    model_check_scope='original_stage_problem')
    best=model.getBestSol()
    return dict(original_model_check=bool(model.checkSol(best,printreason=False,completely=True,original=True)),
                transformed_model_check=bool(model.checkSol(best,printreason=False,completely=True)),
                model_check_scope='original_stage_problem')

def fix_structure(x,reference):
    """Fix the selected finite configuration, retain timing/robot-order choices."""
    if not validate(reference)['valid']:raise ValueError('Reference failed independent physical validation')
    for key in ('load_ports','source','dummy_count','cleaning_interval','full_time','mix_time','cleaning_time','chambers'):
        a=asdict(x.cfg)[key];b=reference['config'][key]
        if json.dumps(a,sort_keys=True)!=json.dumps(b,sort_keys=True):raise ValueError('Fixed baseline has different '+key)
    if x.cfg.vtr_hand_policy!=reference['config'].get('vtr_hand_policy','legacy_unrestricted'):raise ValueError('Fixed baseline has different VTR hand policy')
    pairs={p['id']:p for p in reference['pairs']};cy={(c['chamber'],c['index']):c for c in reference['cycles']}
    if max(pairs,default=-1)>=x.P or max((q for c,q in cy),default=-1)>=x.Q:raise ValueError('Reference exceeds candidate bounds')
    for p in range(x.P):
        chosen=pairs.get(p);x.model.addCons(x.pair.active[p]==int(chosen is not None))
        for r in (0,1):
            w=chosen['members'][r] if chosen else None
            for prod in x.products:x.model.addCons(x.pair.member[prod.identifier,p,r]==int(w==prod.identifier))
            for t in (f'D{i+1}' for i in range(x.cfg.dummy_count)):x.model.addCons(x.pair.dummy_identity[t,p,r]==int(w==t))
        for c in x.cfg.chambers:x.model.addCons(x.pair.chamber[p,c]==int(bool(chosen and chosen['chamber']==c)))
    for (c,q),u in x.cy.used.items():
        chosen=cy.get((c,q));x.model.addCons(u==int(chosen is not None))
        for p in range(x.P):x.model.addCons(x.cy.occupancy[p,c,q]==int(bool(chosen and p in chosen['pairs'])))
        for k in ('4x1','2x2','clean'):
            var=x.cy.kind[c,q,k];value=int(bool(chosen and k==chosen['mode']))
            if isinstance(var,(int,float)):
                if var!=value:raise ValueError('Fixed structure contradicts a propagated recipe')
            else:x.model.addCons(var==value)
        for p in range(x.P):x.model.addCons(x.front[p,c,q]==int(bool(chosen and p==chosen['front'])))

def solve(config_path,out,time_limit=600,stage2_limit=120,seed=1,export_only=False,warm_start=None,fixed=None,memory_mb=16000,method="scip",training_seed=1,initialization="spbs",initialization_budget=60,*,cleaning_rule='optional',cut_profile='root_only',refinement_objective='full'):
    if cleaning_rule not in ('optional','legacy'):raise ValueError('Unknown cleaning rule')
    if cut_profile not in ('root_only','standard'):raise ValueError('Unknown cut profile')
    if refinement_objective not in ('full','waiting_only','quadratic'):raise ValueError('Unknown refinement objective')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    cfg=Config(**json.loads(Path(config_path).read_text(encoding='utf-8-sig')))
    record=policy_record(method,training_seed)
    manifest=dict(method=method,policy=record,initialization=initialization,initialization_budget=initialization_budget,schema=1,config=asdict(cfg),assets=assets(),seed=seed,time_limit=time_limit,stage2_limit=stage2_limit,python=sys.version,platform=platform.platform(),fixed_reference=str(fixed) if fixed else None,warm_start=str(warm_start) if warm_start else None)
    manifest.update(cleaning_rule=cleaning_rule,cut_profile=cut_profile,refinement_objective=refinement_objective)
    if fixed and fixed!='constructed':manifest['fixed_reference_sha256']=digest(Path(fixed))
    if warm_start:manifest['warm_start_sha256']=digest(Path(warm_start))
    dump(out/'manifest.json',manifest);begin=time.monotonic();x=Integrated(cfg);m=x.model
    if cleaning_rule=='legacy':
        # Same expanded candidate capacity in both arms; isolate the trigger rule.
        for c in cfg.chambers:
            for q in range(x.Q):
                prev=x.cy.counter[c,q-1] if q else 0
                k=x.cy.kind[c,q,'clean'];next_mix=x.cy.kind[c,q+1,'2x2'] if q+1<x.Q else 0
                m.addCons(prev>=(cfg.cleaning_interval-1)*k,name=f'legacy_clean_min_{c}_{q}')
                m.addCons(prev+next_mix>=cfg.cleaning_interval*k,name=f'legacy_clean_next_{c}_{q}')
    if fixed:fix_structure(x,construct(cfg) if fixed=='constructed' else json.loads(Path(fixed).read_text(encoding='utf-8')))
    dimensions={'variables':m.getNVars(),'constraints':m.getNConss(),'types':x.original_dimensions['types']};x.original_dimensions=dimensions
    dump(out/'build.json',dict(seconds=time.monotonic()-begin,dimensions=dimensions,safe_bounds=x.safe_bounds,restricted=x.bounded))
    m.setIntParam('randomization/randomseedshift',seed);m.setIntParam('parallel/maxnthreads',1)
    m.setRealParam('limits/memory',memory_mb)
    m.writeProblem(str(out/'model.lp'),verbose=False)
    import gzip,shutil
    with (out/'model.lp').open('rb') as raw,gzip.open(out/'model.lp.gz','wb',compresslevel=1) as compressed:shutil.copyfileobj(raw,compressed)
    (out/'model.lp').unlink()
    m.setLogfile(str(out/'solver.log'))
    manifest['lp_sha256']=digest(out/'model.lp.gz');dump(out/'manifest.json',manifest)
    if export_only:return {'exported':True,'dimensions':dimensions,'output':str(out)}
    seed_started=time.monotonic()
    if initialization!='none' and not warm_start:

        initial=construct(cfg);dump(out/'initial_schedule.json',initial)
        from reference_completion import complete_reference
        serial,initial_values,levels,completion=complete_reference(x,initial,memory_mb,initialization_budget if initialization=='spbs' else 0)
        del serial
        dump(out/'reference_completion.json',completion);dump(out/'spbs_levels.json',levels)
        sol=m.createSol()
        for v in m.getVars(transformed=False):m.setSolVal(sol,v,initial_values[v.name])
        if not m.checkSol(sol,printreason=False,completely=True):raise RuntimeError('Released initial solution failed original MILP constraints')
        m.addSol(sol)
        dump(out/'initial_variables.json',dict(values=initial_values,model_sha256=manifest['lp_sha256']))
    dump(out/'initialization.json',dict(seconds=time.monotonic()-seed_started))
    if warm_start:
        warm=json.loads(Path(warm_start).read_text(encoding='utf-8'))
        if 'values' not in warm:raise ValueError('Warm start must be variables.json from this runner')
        sol=m.createSol()
        for var in m.getVars():m.setSolVal(sol,var,warm['values'].get(var.name,cfg.horizon if var.name.startswith(('empty_boundary_','exchange_boundary_')) else 0))
        accepted=m.checkSol(sol,printreason=False,completely=True)
        dump(out/'warm_start_check.json',dict(accepted=accepted,source=str(warm_start)))
        if accepted:m.addSol(sol)
        else:m.freeSol(sol)
    agent,record=install(m,method,training_seed)
    if cut_profile=='root_only':
        m.setIntParam('separating/maxroundsroot',1);m.setIntParam('separating/maxrounds',0)
    m.setRealParam('limits/time',time_limit);m.optimize()
    primary=x.result();primary['primal_dual_integral']=m.getPrimalDualIntegral() if hasattr(m,'getPrimalDualIntegral') else None
    primary['cleaning_policy']='optional_before_threshold' if cleaning_rule=='optional' else 'legacy_H_or_Hminus1_before_2x2'
    primary.update(incumbent_checks(m))
    if agent is not None:dump(out/'cutsel_telemetry.json',agent.get_telemetry())
    primary['validation']=validate(primary);primary['experiment_scope']='fixed_configuration' if fixed else 'joint'
    dump(out/'phase1.json',finite(primary))
    selected=primary
    if m.getNSols():
        best=m.getBestSol();values={v.name:m.getSolVal(best,v) for v in m.getVars(transformed=False)}
        dump(out/'variables_phase1.json',dict(values=values,model_sha256=manifest['lp_sha256']))
        m.writeBestSol(str(out/'phase1.sol'))
        if not primary['validation']['valid']:raise RuntimeError('Primary physical validation failed; inspect phase1.json')
        if stage2_limit>0:
            incumbent=primary['cmax'];m.freeTransform()
            # Structural binaries, integer counters, resource/slot orders fixed;
            # coordinated handling switches and continuous timing remain free.
            fixed_count=0
            for v in m.getVars(transformed=False):
                if v.vtype()!='CONTINUOUS' and not v.name.startswith('sync_'):
                    val=round(values[v.name]);m.chgVarLb(v,val);m.chgVarUb(v,val);fixed_count+=1
            m.addCons(x.cmax<=incumbent+1e-6)
            objective=x.secondary_objective
            if refinement_objective=='waiting_only':objective=sum(x.waits)+10*x.max_wait
            elif refinement_objective=='quadratic':
                objective=m.addVar(lb=0,name='quadratic_refinement_epigraph')
                m.addCons(objective>=sum(x.waits)+10*x.max_wait+25*sum(v*v for v in x.rhythm))
                base=m.createSol()
                for var in m.getVars(transformed=False):m.setSolVal(base,var,values.get(var.name,0))
                values[objective.name]=sum(m.getSolVal(base,w) for w in x.waits)+10*values[x.max_wait.name]+25*sum(values[v.name]**2 for v in x.rhythm)
                m.freeSol(base)
            m.setObjective(objective,'minimize');m.setRealParam('limits/time',stage2_limit)
            # The first-stage solution remains feasible for the refinement model.
            sol=m.createSol()
            for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
            if m.checkSol(sol,printreason=False,completely=True):m.addSol(sol)
            else:m.freeSol(sol)
            m.optimize();secondary=x.result();secondary['phase']='secondary';secondary['fixed_discrete_variables']=fixed_count
            secondary['cleaning_policy']=primary['cleaning_policy']
            secondary.update(incumbent_checks(m))
            secondary['validation']=validate(secondary);secondary['primary_bound']=primary['dual_bound'];secondary['primary_status']=primary['status']
            secondary['primary_gap']=primary.get('gap');secondary['secondary_objective']=m.getObjVal() if m.getNSols() else None
            dump(out/'phase2.json',finite(secondary))
            if secondary['validation']['valid']:
                selected=secondary;best=m.getBestSol();values={v.name:m.getSolVal(best,v) for v in m.getVars(transformed=False)};m.writeBestSol(str(out/'phase2.sol'))
        dump(out/'variables.json',dict(values=values,model_sha256=manifest['lp_sha256']))
    selected['experiment_scope']='fixed_configuration' if fixed else 'joint'
    selected['primary_bound']=primary['dual_bound'];selected['primary_status']=primary['status'];selected['primary_gap']=primary.get('gap');selected['method']=method;selected['initialization']=initialization;selected['primary_primal_dual_integral']=primary.get('primal_dual_integral')
    selected['result_eligible']=bool(selected['validation']['valid'])
    selected['full_candidate_space']=not x.bounded and not fixed and cleaning_rule=='optional'
    dump(out/'result.json',finite(selected))
    m.freeProb()
    return dict(output=str(out),status=primary['status'],cmax=selected.get('cmax'),valid=selected['validation']['valid'],full_candidate_space=selected['full_candidate_space'],dimensions=dimensions)

def ports(n,recipe):
    d={f'LP{i}':{'4x1':0,'2x2':0} for i in range(1,5)}
    for j in range(n):
        mode=recipe if recipe in ('4x1','2x2') else ('4x1' if j<n//2 else '2x2')
        d[f'LP{j%4+1}'][mode]+=1
    return d

def prepare(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False);(out/'configs').mkdir();cells=[]
    ns=args.sizes or ([2,4,6] if args.suite=='reference' else [8,16,24])
    hs=args.thresholds or ([2,3] if args.suite=='reference' else list(range(3,11)) if args.suite=='crossover' else [3,10])
    for n in ns:
        for h in hs:
            for recipe in args.recipes:
                for source in args.sources:
                    key=f'n{n}_H{h}_{recipe}_{source}';cfg=asdict(Config(ports(n,recipe),source=source,cleaning_interval=h))
                    path=out/'configs'/f'{key}.json';dump(path,cfg)
                    for seed in args.seeds:
                        for method in args.methods:
                            for formulation in args.formulations:
                                cells.append(dict(id=f'{key}_s{seed}_{method}_{formulation}',config=str(path.relative_to(out)),sha256=digest(path),seed=seed,method=method,formulation=formulation))
    dump(out/'campaign.json',dict(schema=1,suite=args.suite,assets=assets(),policy_records={method:policy_record(method,args.training_seed) for method in args.methods},training_seed=args.training_seed,cells=cells))
    print(json.dumps({'campaign':str(out),'cells':len(cells)}))

def _campaign_locked(args):
    out=Path(args.campaign);manifest=json.loads((out/'campaign.json').read_text(encoding='utf-8'))
    if manifest['assets']!=assets():raise RuntimeError('Frozen code changed: prepare a new campaign; existing results retained')
    for method,record in manifest.get('policy_records',{}).items():
        if record!=policy_record(method,manifest.get('training_seed',1)):raise RuntimeError('Frozen policy changed')
    settings={k:getattr(args,k) for k in ('time_limit','stage2_limit','initialization','initialization_budget','memory_mb','export_only')}
    settings_file=out/'execution.json'
    if settings_file.exists():
        if json.loads(settings_file.read_text(encoding='utf-8'))!=settings:raise RuntimeError('Resume budget/settings changed; use a new campaign for a different budget')
    else:dump(settings_file,settings)
    for cell in manifest['cells']:
        cfg=out/cell['config']
        if digest(cfg)!=cell['sha256']:raise RuntimeError('Frozen configuration changed: '+cell['id'])
    for cell in manifest['cells']:
        dest=out/'runs'/cell['id']
        if dest.exists():
            if args.resume and (dest/'result.json').exists():continue
            if args.resume and (dest/'model.lp.gz').exists() and args.export_only:continue
            if not args.resume:raise RuntimeError(f'Existing run {dest}; use --resume')
            # Preserve interrupted attempts, then restart just this cell.
            from datetime import datetime
            archive=out/'interrupted_attempts'/f"{cell['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            if not dest.resolve().is_relative_to(out.resolve()) or not archive.resolve().is_relative_to(out.resolve()):raise RuntimeError('Unsafe campaign path')
            archive.parent.mkdir(exist_ok=True);dest.rename(archive)
        print('START '+cell['id'],flush=True)
        summary=solve(out/cell['config'],dest,args.time_limit,args.stage2_limit,cell['seed'],args.export_only,memory_mb=args.memory_mb,method=cell.get('method','scip'),training_seed=manifest.get('training_seed',1),fixed='constructed' if cell.get('formulation')=='fixed' else None,initialization=args.initialization,initialization_budget=args.initialization_budget)
        print(json.dumps(summary),flush=True)
        import gc
        gc.collect()

def campaign(args):
    # OS-released lock prevents concurrent writers; a crash does not strand it.
    import os
    lock=Path(args.campaign)/'.run.lock'
    with lock.open('a+b') as f:
        if f.tell()==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:raise RuntimeError('This campaign is already running') from exc
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:_campaign_locked(args)
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--suite',choices=['reference','comparison','crossover'],default='comparison');prep.add_argument('--output',required=True)
    prep.add_argument('--sizes',type=int,nargs='+');prep.add_argument('--thresholds',type=int,nargs='+');prep.add_argument('--recipes',nargs='+',choices=['4x1','2x2','mixed'],default=['4x1','2x2','mixed']);prep.add_argument('--sources',nargs='+',choices=['single','dual'],default=['single','dual']);prep.add_argument('--seeds',nargs='+',type=int,default=[1,2,3])
    prep.add_argument('--methods',nargs='+',choices=['scip','hem','proposed'],default=['scip']);prep.add_argument('--formulations',nargs='+',choices=['joint','fixed'],default=['joint']);prep.add_argument('--training-seed',type=int,default=1)
    run=sub.add_parser('run');run.add_argument('--campaign',required=True);run.add_argument('--resume',action='store_true')
    one=sub.add_parser('solve');one.add_argument('--config',required=True);one.add_argument('--output',required=True);one.add_argument('--seed',type=int,default=1);one.add_argument('--warm-start');one.add_argument('--fixed-reference');one.add_argument('--method',choices=['scip','hem','proposed'],default='scip');one.add_argument('--training-seed',type=int,default=1)
    for parser in (run,one):
        parser.add_argument('--initialization',choices=['none','serial','spbs'],default='spbs');parser.add_argument('--initialization-budget',type=float,default=60)
        parser.add_argument('--time-limit',type=float,default=600);parser.add_argument('--stage2-limit',type=float,default=120);parser.add_argument('--memory-mb',type=float,default=16000);parser.add_argument('--export-only',action='store_true')
    a=p.parse_args()
    if a.command=='prepare':prepare(a)
    elif a.command=='run':campaign(a)
    else:print(json.dumps(solve(a.config,a.output,a.time_limit,a.stage2_limit,a.seed,a.export_only,a.warm_start,a.fixed_reference,a.memory_mb,a.method,a.training_seed,a.initialization,a.initialization_budget)))
if __name__=='__main__':main()
