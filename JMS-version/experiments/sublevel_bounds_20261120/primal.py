"""Search a frozen SPBS arrangement for a schedule attaining the global bound.

Integer seconds, membership and cycle occupancy restrict only this primal
search. Only the independent resource bound can certify the continuous model.
"""
import argparse
import math
import sys
import time
from dataclasses import replace
from pathlib import Path
from ortools.sat.python import cp_model
import ortools

from compare import ARCHIVE, GAP, HERE, JMS, attach
from design import read, rel, save, sha, sparse
from bounds import lock_bound

CASES=('D_n2_mixed_scenario3','D_n4_mixed_H10','D_n16_4x1')
OUT=JMS/'results/sublevel_primal_20261120_r1'


def integer(value):
    if abs(value-round(value))>1e-6:
        raise ValueError(f'Nonintegral input to scheduling subproblem: {value}')
    return round(value)


def extract(m, values):
    cp=cp_model.CpModel()
    fixed={}
    varmap={}
    for v in m.getVars(transformed=False):
        if v.vtype() != 'CONTINUOUS' and v.name.startswith(('jp_','pj_','jc_','identity_code_','tail_','carry_')):
            fixed[v.name]=integer(values.get(v.name,0))
            continue
        lo,hi=integer(v.getLbOriginal()),integer(v.getUbOriginal())
        cv=cp.new_bool_var(v.name) if (lo,hi)==(0,1) else cp.new_int_var(lo,hi,v.name)
        varmap[v.name]=cv
        val=values.get(v.name,0)
        if abs(val-round(val))<1e-6:
            cp.add_hint(cv,round(val))
    for row in m.getConss():
        if row.getConshdlrName()!='linear': raise ValueError('Unsupported constraint')
        terms=[];coefs=[];offset=0
        for name,coef in m.getValsLinear(row).items():
            a=integer(coef)
            if name in fixed:
                offset+=a*fixed[name]
            else:
                terms.append(varmap[name]);coefs.append(a)
        l,r=m.getLhs(row),m.getRhs(row)
        lo=integer(l)-offset if l>-1e19 else cp_model.INT_MIN
        hi=integer(r)-offset if r<1e19 else cp_model.INT_MAX
        if not terms:
            if not lo<=0<=hi: raise ValueError('Frozen structure contradicts the original rows')
            continue
        cp.add_linear_constraint(cp_model.LinearExpr.weighted_sum(terms,coefs),lo,hi)
    if cp.validate(): raise ValueError(cp.validate())
    return cp,fixed,varmap


def run(case,seconds):
    sys.path.insert(0,str(JMS/'model4_pjob_nonprocessing_20261103'))
    import model
    from validate import validate
    prep=ARCHIVE/'runs'/case/'prep'
    ev=read(prep/'evidence.json')
    assert ev['valid'] and sha(prep/'schedule.json')==ev['schedule_sha256'] and sha(prep/'assignment.json.gz')==ev['assignment_sha256']
    data=read(prep/'schedule.json')
    vals=read(prep/'assignment.json.gz')['nonzero']
    cfg=model.Config(**read(ARCHIVE/'protocol.json')['cases'][case]['config'])
    dest=OUT/case
    dest.mkdir(parents=True,exist_ok=False)
    begun=time.monotonic()
    bound=lock_bound(cfg)['lower']
    ub=ev['metrics']['cmax']
    checks=validate(data)
    if not checks['valid']:raise ValueError(checks['errors'])
    active_pairs=max(max(p['id'] for p in data['pairs'])+1,sum(j['product'] for j in data['jobs']))
    active_cycles=max(c['index'] for c in data['cycles'])+1
    reduced=model.Integrated(replace(cfg,max_pairs=active_pairs,max_cycles=active_cycles))
    cp,fixed,varmap=extract(reduced.model,vals)
    cp.add(varmap['Cmax']<=math.floor(bound*(1+GAP)+1e-7))
    solver=cp_model.CpSolver()
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=seconds
    solver.parameters.max_memory_in_mb=512
    status=solver.solve(cp)
    searched=time.monotonic()-begun
    feasible=status in (cp_model.OPTIMAL,cp_model.FEASIBLE)
    reduced.model.freeProb()
    if feasible:
        candidate=dict(fixed)
        candidate.update((name,solver.value(cv)) for name,cv in varmap.items())
        for c in cfg.chambers:
            candidate[f'empty_boundary_{c}_{active_cycles}']=cfg.horizon
        original=model.Integrated(cfg)
        sol=attach(original.model,candidate)
        data=original.result(solution=sol)
        checks=validate(data)
        if not checks['valid']:raise ValueError(checks['errors'])
        ub=checks['product_return_cmax']
        if abs(ub-candidate['Cmax'])>2e-4:raise ValueError('Physical objective and CP assignment differ')
        full={v.name:original.model.getSolVal(sol,v) for v in original.model.getVars(transformed=False)}
        save(dest/'assignment.json.gz',sparse(full))
        save(dest/'schedule.json',data)
        original.model.freeSol(sol);original.model.freeProb()
    save(dest/'result.json',dict(case=case,input_sha256=ev['assignment_sha256'],
         input=rel(prep),initial_upper=ev['metrics']['cmax'],upper=ub,global_lower=bound,
         gap=(ub-bound)/bound,gate=(ub-bound)/bound<=GAP+1e-9,
         solver_seconds=solver.wall_time,wall_to_candidate_s=searched,total_verified_s=time.monotonic()-begun,
         local_status=solver.status_name(status),new_witness=feasible,limit_s=seconds,workers=1,seed=1,
         target=GAP,params='integer seconds; fixed pair composition, identity, chamber and cycle occupancy; free timing and handling order',
         cp_vars=len(cp.proto.variables),cp_rows=len(cp.proto.constraints),ortools=ortools.__version__,
         policy='shared frozen SPBS input; no learned cut selection during CP proposal',
         source_sha256=sha(Path(__file__)),bounds_sha256=sha(HERE/'bounds.py'),
         assignment_sha256=sha(dest/'assignment.json.gz') if feasible else None,
         schedule_sha256=sha(dest/'schedule.json') if feasible else None,replay=checks))
    print(case,solver.status_name(status),'global',bound,ub,'wall',time.monotonic()-begun,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--seconds',type=int,default=20)
    parser.add_argument('--cases',nargs='+',choices=CASES,default=CASES[:2])
    args=parser.parse_args()
    for n,case in enumerate(args.cases):
        print(f'Completed {n}/{len(args.cases)}, failed 0 | {case} | remaining search budget {(len(args.cases)-n)*args.seconds}s + reconstruction',flush=True)
        run(case,args.seconds)
    print(f'Completed {len(args.cases)}/{len(args.cases)}, failed 0',flush=True)
