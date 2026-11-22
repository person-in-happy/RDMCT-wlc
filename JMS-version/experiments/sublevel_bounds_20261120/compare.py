"""Paired one-CPU first-stage comparison from the same frozen SPBS solutions."""
import argparse
import gc
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
sys.path.insert(0, str(HERE.parent/'manuscript_certified_gaps_20261119'))
from design import OUT as ARCHIVE, read, rel, save, sha, sparse
from bounds import capacity, lock_bound, strengthen

OUT = JMS/'results/sublevel_bounds_20261120_r1'
CASES = ('D_n2_mixed_scenario3', 'D_n4_mixed_H10')
ARMS = ('original', 'bounded')
GAP = 0.0001


def attach(m, values):
    sol = m.createSol()
    for v in m.getVars(transformed=False):
        m.setSolVal(sol, v, values.get(v.name, 0.))
    if not m.checkSol(sol, printreason=False, completely=True, original=True):
        raise ValueError('Assignment failed the original SCIP rows')
    return sol


def run(case_id, arm, seconds):
    from worker import install_cpu, route_bound
    from gap_two_stage import f
    sys.path.insert(0,str(f.BACKENDS['D']))
    import model
    from validate import validate
    import pyscipopt
    import psutil
    case = read(ARCHIVE/'protocol.json')['cases'][case_id]
    prep = ARCHIVE/'runs'/case_id/'prep'
    seed = read(prep/'evidence.json')
    if not seed['valid'] or sha(prep/'assignment.json.gz') != seed['assignment_sha256'] or sha(prep/'schedule.json') != seed['schedule_sha256']:
        raise ValueError('Frozen initialization mismatch')
    start = read(prep/'schedule.json')
    initial = read(prep/'assignment.json.gz')['nonzero']
    cfg = model.Config(**case['config'])
    if case['backend'] != 'D' or not validate(start)['valid']:
        raise ValueError('Invalid backend or starting schedule')
    upper = seed['metrics']['cmax']
    dest = OUT/case_id/arm
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    plan = capacity(cfg, upper) if arm == 'bounded' else None
    actual = replace(cfg, max_pairs=plan['pairs'], max_cycles=plan['cycles']) if plan else cfg
    x = model.Integrated(actual)
    m = x.model
    m.setIntParam('parallel/maxnthreads',1)
    m.setIntParam('lp/threads',1)
    m.setIntParam('randomization/randomseedshift',1)
    m.setIntParam('timing/clocktype',2)
    m.setRealParam('limits/memory',case['scip_memory_mib'])
    m.setRealParam('limits/time',seconds)
    m.setRealParam('limits/gap',GAP)
    m.setRealParam('limits/absgap',0.)
    m.setObjective(x.primary_objective,'minimize')
    m.setLogfile(str(dest/'scip.log'))
    m.addCons(x.cmax >= route_bound(x),name='mandatory_serial_AL_and_last_product_route')
    if plan:
        strengthen(x,plan,start,upper)
    agent, policy = install_cpu(m, 'proposed')
    if not m.addSol(attach(m,initial)):
        raise ValueError('Warm solution not accepted')
    raw = dict(variables=m.getNVars(),rows=m.getNConss(),pairs=x.P,cycles=x.Q)
    before_search = time.monotonic()-t0
    m.optimize()
    t_search = m.getSolvingTime()
    dual, primal, status = m.getDualbound(),m.getPrimalbound(),str(m.getStatus())
    if not m.getNSols() or not 0 < dual <= primal+2e-4:
        raise ValueError('Invalid bounds')
    best = m.getBestSol()
    values = {v.name:m.getSolVal(best,v) for v in m.getVars(transformed=False)}
    search = dict(nodes=m.getNNodes(),lp_iterations=m.getNLPIterations(),lp_solves=m.getNLPs())
    metrics = agent.get_telemetry()
    save(dest/'telemetry.json',metrics)
    m.freeProb()
    del m,x,best,agent
    gc.collect()
    # Lift the witness and check the unrestricted model, including the extra
    # empty-boundary variable immediately after the last compact cycle.
    original = model.Integrated(cfg)
    for c in cfg.chambers:
        if plan and plan['cycles'] < original.Q:
            values[f"empty_boundary_{c}_{plan['cycles']}"] = cfg.horizon
    projected = attach(original.model,values)
    restored = original.result(solution=projected)
    replay = validate(restored)
    if not replay['valid'] or abs(replay['product_return_cmax']-primal)>2e-4:
        raise ValueError('Unrestricted model replay mismatch')
    # Save a full-domain witness, independent of any solver-bound certificate.
    values = {v.name:original.model.getSolVal(projected,v) for v in original.model.getVars(transformed=False)}
    save(dest/'assignment.json.gz',sparse(values))
    save(dest/'schedule.json',restored)
    gap = max(0.,primal-dual)/dual
    save(dest/'result.json',dict(case=case_id,arm=arm,status=status,threshold=GAP,
        lower=dual,upper=primal,gap=gap,gate=gap<=GAP+1e-9,
        limit_s=seconds,solver_s=t_search,wall_s=time.monotonic()-t0,
        build_and_policy_s=before_search,raw=raw,search=search,capacity=plan,
        independent_lock_bound=lock_bound(cfg),replay=replay,full_rows=original.model.getNConss(),
        source=rel(prep),input_sha256=seed['assignment_sha256'],
        checkpoint_sha256=sha(policy['checkpoint']),protocol_sha256=sha(ARCHIVE/'protocol.json'),
        script_sha256=sha(Path(__file__)),bounds_sha256=sha(HERE/'bounds.py'),
        model_sha256=sha(Path(model.__file__)),pyscipopt=pyscipopt.__version__,
        cpus=1,gpu=False,scip_memory_mib=case['scip_memory_mib'],seed=1,
        peak_working_mib=psutil.Process().memory_info().peak_wset/2**20,
        assignment_sha256=sha(dest/'assignment.json.gz'),schedule_sha256=sha(dest/'schedule.json')))
    original.model.freeSol(projected)
    original.model.freeProb()


def campaign(seconds):
    OUT.mkdir(parents=True,exist_ok=True)
    spec=dict(cases=CASES,arms=ARMS,solver_seconds=seconds,threshold=GAP,concurrency=2,
              cpu_threads_per_job=1,solver_seed=1,training_seed=1,gpu=False,
              source=rel(ARCHIVE),script_sha256=sha(Path(__file__)),bounds_sha256=sha(HERE/'bounds.py'))
    manifest=OUT/'campaign.json'
    import json
    if manifest.exists() and read(manifest)!=json.loads(json.dumps(spec)):
        raise ValueError('Existing comparison has different settings')
    save(manifest,spec)
    finished=failed=0
    for index,case in enumerate(CASES):
        running={}
        for arm in ARMS:
            dest=OUT/case/arm
            if (dest/'result.json').exists():
                finished+=1
                continue
            dest.mkdir(parents=True,exist_ok=True)
            log=(dest/'worker.log').open('w',encoding='utf-8')
            proc=subprocess.Popen([sys.executable,'-B','-X','utf8','-u',__file__,'--case',case,
                                   '--arm',arm,'--seconds',str(seconds)],stdout=log,stderr=subprocess.STDOUT)
            running[arm]=(proc,log)
        start=time.monotonic()
        while running:
            for arm,(proc,log) in list(running.items()):
                if proc.poll() is not None:
                    log.close()
                    if proc.returncode: failed+=1
                    else: finished+=1
                    del running[arm]
            remain=max(0,seconds-(time.monotonic()-start))+(len(CASES)-index-1)*seconds
            print(f'{case} | active {list(running)} | completed {finished}/4 | failed {failed} | remaining budget ~{remain:.0f}s + build/verification',flush=True)
            if running: time.sleep(5)
    if failed:
        raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--case',choices=CASES)
    parser.add_argument('--arm',choices=ARMS)
    parser.add_argument('--seconds',type=int,default=120)
    args=parser.parse_args()
    if args.case: run(args.case,args.arm,args.seconds)
    else: campaign(args.seconds)
