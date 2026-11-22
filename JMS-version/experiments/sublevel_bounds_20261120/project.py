"""Continuous-model lower bounds from an integer outer relaxation and checked witnesses.

The proof export retains only difference rows in continuous columns. After
fixing the integers in any original solution, flooring all timestamps keeps
such rows valid. A primal CP solution is always checked against full D rows.
"""
import argparse
import gc
import math
import platform
import sys
import time
from dataclasses import replace
from pathlib import Path

import ortools
from ortools.sat.python import cp_model

from compare import ARCHIVE, GAP, HERE, JMS
from design import read, rel, save, sha, sparse
from bounds import capacity, lock_bound, strengthen

OUT=JMS/'results/sublevel_projection_20261120_r1'
CASES=('D_n2_mixed_scenario3','D_n4_mixed_H10','D_n16_4x1')


def export(x, initial):
    m=x.model
    cp=cp_model.CpModel()
    varmap={}
    real=set()
    derived={x.max_wait.name,*(v.name for v in x.rhythm)}
    for var in m.getVars(transformed=False):
        if var.name in derived:
            continue
        lo,hi=math.floor(var.getLbOriginal()),math.ceil(var.getUbOriginal())
        cv=cp.new_bool_var(var.name) if (lo,hi)==(0,1) else cp.new_int_var(lo,hi,var.name)
        varmap[var.name]=cv
        if var.vtype()=='CONTINUOUS':
            real.add(var.name)
        cp.add_hint(cv,min(hi,max(lo,math.floor(initial.get(var.name,0.)+1e-7))))
    counts={'difference_rows':0,'integer_rows':0,'projected_helper_rows':0,'outward_rows':0}
    for row in m.getConss():
        if row.getConshdlrName()!='linear': raise ValueError('Nonlinear source row')
        coeff=m.getValsLinear(row)
        if derived.intersection(coeff):
            counts['projected_helper_rows']+=1
            continue
        timing=sorted(value for name,value in coeff.items() if name in real)
        if timing not in ([],[-1.],[1.],[-1.,1.]):
            raise ValueError(f'Unexpected physical time row {row.name}: {timing}')
        counts['difference_rows' if timing else 'integer_rows']+=1
        # Replace any nonintegral coefficient by the nearest integer and
        # widen the row by its maximum signed error on the variable domain.
        low_error=high_error=0.
        cv=[];weights=[]
        for name,value in coeff.items():
            a=round(value)
            if a!=value:
                if name in real: raise ValueError('Nonunit physical coefficient')
                domain=varmap[name].proto.domain
                err=[(a-value)*domain[0],(a-value)*domain[-1]]
                low_error+=min(err);high_error+=max(err)
            weights.append(a);cv.append(varmap[name])
        lb,ub=m.getLhs(row),m.getRhs(row)
        lo=cp_model.INT_MIN if lb < -1e19 else math.floor(lb+low_error)
        hi=cp_model.INT_MAX if ub > 1e19 else math.ceil(ub+high_error)
        if low_error or high_error: counts['outward_rows']+=1
        cp.add_linear_constraint(cp_model.LinearExpr.weighted_sum(cv,weights),lo,hi)
    cp.minimize(varmap[x.cmax.name])
    if cp.validate():raise ValueError(cp.validate())
    return cp,varmap,counts


def verify_full(cfg, values, compact_q):
    import model
    from validate import validate
    full=model.Integrated(cfg)
    m=full.model
    if compact_q<full.Q:
        for c in cfg.chambers:
            values[f'empty_boundary_{c}_{compact_q}']=cfg.horizon
    s=m.createSol()
    vs=m.getVars(transformed=False)
    for v in vs:
        m.setSolVal(s,v,values.get(v.name,0.))
    val=lambda e:m.getSolVal(s,e)
    m.setSolVal(s,full.max_wait,max(val(w) for w in full.waits))
    by_name={v.name:v for v in vs}
    for c in cfg.chambers:
        for q in range(2,full.Q):
            active=val(full.keep[c,q])>.5 and val(full.keep[c,q-1])>.5
            delta=val(full.cy.start[c,q])-2*val(full.cy.start[c,q-1])+val(full.cy.start[c,q-2])
            m.setSolVal(s,by_name[f'rhythm_{c}_{q}'],abs(delta) if active else 0.)
    good=m.checkSol(s,printreason=False,completely=True,original=True)
    data=full.result(solution=s) if good else None
    checks=validate(data) if good else {'valid':False}
    witness=sparse({v.name:val(v) for v in vs}) if checks['valid'] else None
    rows=m.getNConss()
    m.freeSol(s);m.freeProb()
    return data,checks,witness,rows


def run(case,seconds,proposal):
    sys.path.insert(0,str(JMS/'model4_pjob_nonprocessing_20261103'))
    import model
    from validate import validate
    mode='proposal' if proposal else 'complete'
    dest=OUT/case/mode
    if (dest/'result.json').exists():
        raise FileExistsError(dest/'result.json')
    dest.mkdir(parents=True,exist_ok=True)
    prep=ARCHIVE/'runs'/case/'prep'
    ev=read(prep/'evidence.json')
    if not ev['valid'] or sha(prep/'schedule.json')!=ev['schedule_sha256'] or sha(prep/'assignment.json.gz')!=ev['assignment_sha256']:
        raise ValueError('Unmatched SPBS evidence')
    data=read(prep/'schedule.json')
    initial=read(prep/'assignment.json.gz')['nonzero']
    cfg=model.Config(**read(ARCHIVE/'protocol.json')['cases'][case]['config'])
    if not validate(data)['valid']: raise ValueError('Initial solution failed replay')
    start=time.monotonic()
    # Outward integer cap for the continuous incumbent sublevel.
    upper=math.ceil(ev['metrics']['cmax'])
    plan=capacity(cfg,upper)
    p,q=plan['pairs'],plan['cycles']
    if proposal:
        # These extra restrictions are primal-only, so this solver's dual
        # bound and any infeasibility conclusion have no global use.
        p=max(max(pair['id'] for pair in data['pairs'])+1,sum(j['product'] for j in data['jobs']))
        q=max(c['index'] for c in data['cycles'])+1
    x=model.Integrated(replace(cfg,max_pairs=p,max_cycles=q))
    strengthen(x,plan,data,upper)
    cp,vm,audit=export(x,initial)
    x.model.freeProb()
    del x
    gc.collect()
    solver=cp_model.CpSolver()
    solver.parameters.random_seed=1
    solver.parameters.num_search_workers=1
    solver.parameters.max_time_in_seconds=seconds
    solver.parameters.max_memory_in_mb=768
    solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    with (dest/'solver.log').open('w',encoding='utf-8',buffering=1) as stream:
        solver.log_callback=lambda line:stream.write(line.rstrip()+'\n')
        status=solver.solve(cp)
    searched=time.monotonic()-start
    if status in (cp_model.MODEL_INVALID,cp_model.INFEASIBLE) and not proposal:
        raise ValueError('Complete relaxation excluded a known feasible solution')
    bound=lock_bound(cfg)['lower']
    if not proposal: bound=max(bound,solver.best_objective_bound)
    ub=ev['metrics']['cmax'];new=False;checks=None;rows=None
    if status in (cp_model.FEASIBLE,cp_model.OPTIMAL):
        values={n:solver.value(v) for n,v in vm.items()}
        restored,checks,witness,rows=verify_full(cfg,values,q)
        if checks['valid'] and checks['product_return_cmax']<ub+1e-6:
            save(dest/'assignment.json.gz',witness);save(dest/'schedule.json',restored)
            ub=checks['product_return_cmax'];new=True
    if bound>ub+2e-4:raise ValueError('Certified lower bound exceeds verified incumbent')
    gap=max(0.,ub-bound)/bound
    save(dest/'result.json',dict(case=case,mode=mode,status=solver.status_name(status),
        limit_s=seconds,initial_upper=ev['metrics']['cmax'],upper=ub,lower=bound,gap=gap,gate=gap<=GAP+1e-9,
        cp_primal=solver.objective_value if status in (cp_model.FEASIBLE,cp_model.OPTIMAL) else None,
        cp_dual=solver.best_objective_bound,solver_s=solver.wall_time,wall_through_search_s=searched,
        verified_wall_s=time.monotonic()-start,cp_vars=len(vm),cp_rows=len(cp.proto.constraints),
        cp_branches=solver.num_branches,threshold=GAP,source=rel(prep),input_sha256=ev['assignment_sha256'],
        capacity=plan,actual_pairs=p,actual_cycles=q,export_audit=audit,replay=checks,full_rows=rows,
        new_witness=new,schedule_sha256=sha(dest/'schedule.json') if new else None,
        assignment_sha256=sha(dest/'assignment.json.gz') if new else None,ortools=ortools.__version__,
        python=platform.python_version(),scip_model_sha256=sha(Path(model.__file__)),worker_sha256=sha(Path(__file__)),
        bounds_sha256=sha(HERE/'bounds.py'),seed=1,workers=1,gpu=False,cp_memory_mib=768))
    print(case,mode,solver.status_name(status),f'global [{bound:g},{ub:g}] gap {100*gap:.3f}% | verified {time.monotonic()-start:.2f}s',flush=True)


if __name__=='__main__':
    arg=argparse.ArgumentParser(__doc__)
    arg.add_argument('--seconds',type=int,default=90)
    arg.add_argument('--cases',nargs='+',choices=CASES,default=CASES[:2])
    arg.add_argument('--proposal',action='store_true')
    opts=arg.parse_args()
    for n,case in enumerate(opts.cases):
        print(f'Completed {n}/{len(opts.cases)}, failed 0 | {case} | remaining budget {(len(opts.cases)-n)*opts.seconds}s + validation',flush=True)
        run(case,opts.seconds,opts.proposal)
    print(f'Completed {len(opts.cases)}/{len(opts.cases)}, failed 0',flush=True)
