"""Connect frozen HEM/proposed policies to the new model without legacy timing code."""
from pathlib import Path
from types import SimpleNamespace
import csv,hashlib,sys
ROOT=Path(__file__).resolve().parents[2]

def policy_record(method,training_seed=1):
    if method=='scip':return None
    if method not in ('hem','proposed','feature_only','proposed_greedy','proposed_no_structure'):
        raise ValueError('Unknown method: '+method)
    family=method if method in ('hem','feature_only') else 'proposed'
    path=ROOT/'cie/results/repro_manifest/selected_checkpoint_manifest.csv'
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
    matches=[r for r in rows if r['family']==family and int(r['training_seed'])==training_seed]
    if len(matches)!=1:raise ValueError(f'Expected one frozen {family} checkpoint for seed {training_seed}')
    r=matches[0];checkpoint=ROOT/r['checkpoint']
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=r['checkpoint_sha256']:raise ValueError('Checkpoint hash mismatch')
    config=ROOT/('cie/configs/cie_hem_train.json' if method=='hem' else 'cie/configs/cie_proposed_inference.json')
    return dict(method=method,training_seed=training_seed,checkpoint=str(checkpoint),sha256=r['checkpoint_sha256'],config=str(config),config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),transfer='frozen_policy_evaluation_on_new_model')

def install(model,method,training_seed=1):
    record=policy_record(method,training_seed)
    if record is None:return None,None
    sys.path.insert(0,str(ROOT/'cie/code'))
    from run_cie_benchmarks import _load_policy_bundle,_build_agent
    bundle=_load_policy_bundle(record['config'],record['checkpoint'],13 if method=='hem' else 23,'with_token','none' if method in ('hem','feature_only') else 'role_submodular_v1','cuda:0')
    args=SimpleNamespace(sel_cuts_percent=.2,decode_type='greedy' if method in ('hem','feature_only','proposed_greedy') else 'beam_search',policy_type='with_token',cutsel_max_candidates=128,cutsel_max_selected_cuts=16,structure_pool_factor=2.,structure_anchor_ratio=.25,structure_quality_weight=.35,structure_policy_weight=.20,structure_coverage_weight=.25,structure_representation_weight=.20)
    agent=_build_agent(SimpleNamespace(m=model),bundle,args,method in ('proposed','proposed_greedy'))
    model.includeCutsel(cutsel=agent,name='joint_learned_cutsel',desc='Frozen policy on joint model',priority=666666)
    return agent,record

def improve_skeleton(x,values,budget):
    """Five nested structure-preserving neighborhoods, initialization only.

Fixed sets shrink monotonically: release VTR orders, then LL orders, then all
orders, then slot/side and cycle-membership choices. Main solve releases every
extra constraint. Returns the best complete assignment found.
"""
    import time
    m=x.model;records=[];started=time.monotonic()
    if budget<=0:return values,records
    vtr_names={e['name'] for e in x.robots['VTR']}
    def fixed(name,level):
        if name.startswith('sync_'):return False
        if level>=2 and name.startswith('order_') and any(name.startswith('order_'+e+'_') for e in vtr_names):return False
        if level>=3 and name.startswith(('order_U_','order_L_')):return False
        if level>=4 and name.startswith('order_'):return False
        if level>=5:return name.startswith(('jp_','jc_used_','jc_kind_'))
        return True
    for level in range(1,6):
        left=budget-(time.monotonic()-started)
        if left<=0:break
        constraints=[]
        for v in m.getVars(transformed=False):
            if v.vtype()!='CONTINUOUS' and fixed(v.name,level):
                constraints.append((v,v.getLbOriginal(),v.getUbOriginal()));value=round(values[v.name]);m.chgVarLb(v,value);m.chgVarUb(v,value)
        m.setObjective(x.primary_objective,'minimize');m.setRealParam('limits/time',min(left,budget/5))
        sol=m.createSol()
        for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
        if m.checkSol(sol,printreason=False,completely=True):m.addSol(sol)
        else:m.freeSol(sol)
        m.optimize();row=dict(level=level,status=str(m.getStatus()),fixed=len(constraints),seconds=m.getSolvingTime())
        if m.getNSols():
            sol=m.getBestSol();values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)};row['cmax']=values['Cmax']
        records.append(row);m.freeTransform()
        for v,lb,ub in constraints:m.chgVarLb(v,lb);m.chgVarUb(v,ub)
    return values,records
