"""Test the suboptimal cutoff on the unrestricted D model without capacity or symmetry reductions."""
import argparse
import math
import sys
import time
from pathlib import Path
from ortools.sat.python import cp_model
from compare import ARCHIVE, HERE, JMS
from design import read, save, sha


def run(case,seconds):
    sys.path.insert(0,str(JMS/'model4_pjob_nonprocessing_20261103'))
    import model
    source=JMS/'results/sublevel_projection_20261120_r1'/case/'complete'/'result.json'
    proof=read(source)
    if not proof['gate'] or not proof['new_witness'] or abs(proof['upper']-round(proof['upper']))>1e-7:
        raise ValueError('Expected verified integral incumbent')
    cap=round(proof['upper'])-1
    dest=source.parent.parent/'countercheck'
    dest.mkdir(exist_ok=False)
    t0=time.monotonic()
    cfg=model.Config(**read(ARCHIVE/'protocol.json')['cases'][case]['config'])
    x=model.Integrated(cfg);m=x.model
    cp=cp_model.CpModel()
    helpers={x.max_wait.name,*(v.name for v in x.rhythm)}
    variables={v.name:v for v in m.getVars(transformed=False)}
    cmap={n:cp.new_int_var(math.floor(v.getLbOriginal()),math.ceil(v.getUbOriginal()),n)
          for n,v in variables.items() if n not in helpers}
    retained=0
    for row in m.getConss():
        if row.getConshdlrName()!='linear':raise ValueError(row.name)
        coefficients=m.getValsLinear(row)
        if helpers.intersection(coefficients):continue
        times=[a for n,a in coefficients.items() if variables[n].vtype()=='CONTINUOUS']
        if len(times)>2 or any(abs(t)!=1 for t in times) or (len(times)==2 and sum(times)!=0):
            raise ValueError('Unexpected time relation')
        if any(a!=round(a) for a in coefficients.values()):raise ValueError('Noninteger original coefficient')
        lo,hi=m.getLhs(row),m.getRhs(row)
        if lo>-1e19 and lo!=round(lo) or hi<1e19 and hi!=round(hi):raise ValueError('Noninteger original RHS')
        expr=cp_model.LinearExpr.weighted_sum([cmap[n] for n in coefficients],[int(a) for a in coefficients.values()])
        cp.add_linear_constraint(expr,cp_model.INT_MIN if lo<-1e19 else int(lo),cp_model.INT_MAX if hi>1e19 else int(hi))
        retained+=1
    cp.add(cmap['Cmax']<=cap)
    dim=(m.getNVars(),m.getNConss())
    m.freeProb()
    solver=cp_model.CpSolver()
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=7
    solver.parameters.max_time_in_seconds=seconds
    solver.parameters.max_memory_in_mb=1536
    solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    with (dest/'solver.log').open('w',encoding='utf-8',buffering=1) as log:
        solver.log_callback=lambda line:log.write(line.rstrip()+'\n')
        status=solver.solve(cp)
    save(dest/'result.json',dict(case=case,status=solver.status_name(status),cutoff=cap,
         unrestricted_variables=dim[0],unrestricted_rows=dim[1],retained_rows=retained,
         added_resource_bounds=False,capacity_reduction=False,symmetry_fix=False,initial_solution=None,
         solver_s=solver.wall_time,wall_s=time.monotonic()-t0,seed=7,workers=1,
         seconds=seconds,source_sha256=sha(source),script_sha256=sha(Path(__file__))))
    print(case,cap,solver.status_name(status),solver.wall_time,flush=True)
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):raise ValueError('Counterexample to reported certificate')


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--seconds',type=int,default=120)
    args=p.parse_args()
    for i,case in enumerate(('D_n2_mixed_scenario3','D_n4_mixed_H10')):
        print(f'Completed {i}/2, failed 0 | {case} | remaining budget {(2-i)*args.seconds}s + export',flush=True)
        run(case,args.seconds)
    print('Completed 2/2',flush=True)
