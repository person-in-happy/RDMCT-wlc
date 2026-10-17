"""Recover timing from a saved discrete assignment without altering raw runs."""
from pathlib import Path
import argparse,json,time
from model import Config,Integrated
from validate import validate
from run_experiments import assets,digest,dump,finite
from run_matched_supplement import output_lock

def run(source,output,limit):
    source=Path(source).resolve();output=Path(output).resolve()
    if output==source or source in output.parents:raise ValueError('Use a separate recovery directory')
    raw=source/'phase1.json';vf=source/'variables_phase1.json'
    data=json.loads(raw.read_text());values=json.loads(vf.read_text())['values']
    manifest=json.loads((source/'manifest.json').read_text())
    if manifest['assets']!=assets():raise RuntimeError('Source model assets differ; recovery needs the original model')
    protocol=dict(source=str(source),phase1_sha256=digest(raw),variables_sha256=digest(vf),assets=assets(),recovery_sha256=digest(Path(__file__)),time_limit=limit,feastol=1e-9)
    with output_lock(output):
        pf=output/'protocol.json'
        if pf.exists() and json.loads(pf.read_text())!=protocol:raise RuntimeError('Recovery protocol changed')
        dump(pf,protocol)
        rf=output/'result.json'
        if rf.exists() and validate(json.loads(rf.read_text()))['valid']:
            print('REUSE '+str(output));return
        started=time.monotonic();x=Integrated(Config(**data['config']));m=x.model
        m.setRealParam('numerics/feastol',1e-9)
        m.setRealParam('limits/time',limit);m.setRealParam('limits/memory',24000)
        m.setIntParam('parallel/maxnthreads',1)
        count=0
        for v in m.getVars(transformed=False):
            if v.name not in values:raise ValueError('Variable inventory differs')
            if v.vtype()!='CONTINUOUS':
                value=values[v.name]
                if abs(value-round(value))>1e-4:raise ValueError('Nonintegral structure: '+v.name)
                m.chgVarLb(v,round(value));m.chgVarUb(v,round(value));count+=1
        m.addCons(x.cmax<=data['cmax']+1e-6)
        deviations=[]
        for v in list(m.getVars(transformed=False)):
            if v.vtype()=='CONTINUOUS':
                delta=m.addVar('recovery_deviation_'+v.name,lb=0)
                m.addCons(delta>=v-values[v.name]);m.addCons(delta>=values[v.name]-v)
                deviations.append(delta)
        m.setObjective(sum(deviations),'minimize');m.setLogfile(str(output/'solver.log'));m.optimize()
        result=x.result();result['validation']=validate(result)
        result.update(experiment_scope='fixed_discrete_timing_recovery',full_candidate_space=False,benchmark_eligible=False,fixed_discrete_variables=count,source_cmax=data['cmax'],elapsed_seconds=time.monotonic()-started)
        # A fixed-structure bound is never a bound for the original free model.
        result['fixed_structure_dual_bound']=result.pop('dual_bound',None)
        result['fixed_structure_gap']=result.pop('gap',None)
        dump(output/'recovery_attempt.json',finite(result))
        if not result['validation']['valid']:raise RuntimeError('Recovery failed independent validation; original data retained')
        sol=m.getBestSol();dump(output/'variables.json',dict(values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False) if v.name in values},source_model_sha256=manifest['lp_sha256']))
        dump(rf,finite(result));print(json.dumps(dict(output=str(output),cmax=result['cmax'],validation=result['validation'],benchmark_eligible=False)))
        m.freeProb()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--time-limit',type=float,default=30)
    a=p.parse_args();run(a.source,a.output,a.time_limit)
