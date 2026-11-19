"""Projection certificates and independently checked MIP candidates in model D."""
from contextlib import contextmanager
import argparse
import threading
import time
import traceback
from slices import Config, Integrated, JMS, ROOT, TOL, digest, log, np, physical_metrics, read, save, validate
from pathlib import Path

@contextmanager
def progress(out, text, completed, total, budget):
    done=threading.Event()
    start=time.monotonic()
    def beat():
        while not done.wait(12):
            elapsed=time.monotonic()-start
            log(out,f'{text} completed={completed}/{total} failed=0 elapsed={elapsed:.0f}s allocation ETA={max(0,budget-elapsed):.0f}s')
    thread=threading.Thread(target=beat,daemon=True)
    thread.start()
    try: yield
    finally: done.set(); thread.join()

def expression_value(x,sol,expr):
    return float(expr) if isinstance(expr,(int,float)) else x.model.getSolVal(sol,expr)

def set_assignment(x,vals):
    m=x.model; sol=m.createSol()
    for v in m.getVars(transformed=False): m.setSolVal(sol,v,float(vals[v.name]))
    return sol

def physically_checked(x,vals):
    m=x.model; sol=set_assignment(x,vals)
    try:
        if not m.checkSol(sol,printreason=True,completely=True,original=True):raise ValueError('Original rows rejected')
        d=x.result(solution=sol); result=validate(d)
        if not result['valid']:raise ValueError(result)
        metrics=physical_metrics(d)
        vals[x.cmax.name]=metrics['cmax'];vals[x.max_wait.name]=metrics['wait_max']
        for c in x.cfg.chambers:
            for q in range(2,x.Q):
                active=expression_value(x,sol,x.keep[c,q])>.5 and expression_value(x,sol,x.keep[c,q-1])>.5
                value=abs(expression_value(x,sol,x.cy.start[c,q]-2*x.cy.start[c,q-1]+x.cy.start[c,q-2])) if active else 0
                vals[f'rhythm_{c}_{q}']=value
        d['validation']=result
    finally:m.freeSol(sol)
    replay=set_assignment(x,vals)
    try:
        assert m.checkSol(replay,printreason=True,completely=True,original=True)
        assert abs(m.getSolVal(replay,x.secondary_objective)-metrics['secondary'])<TOL
        d['cmax']=metrics['cmax']
    finally:m.freeSol(replay)
    return metrics,d

def read_candidates(data,meta):
    records=[]
    for i,s in enumerate(meta['slices']):
        z=np.load(data/f'slice_{i:03}.npz')
        for j,(a,b) in enumerate(s['vertices']):
            v=np.empty(len(meta['variables']))
            v[meta['continuous_indices']]=z['v'][j];v[meta['discrete_indices']]=z['d']
            records.append((a,b,dict(zip(meta['variables'],v))))
    return records

def pair_family(x,warm):
    # In the two-product PP class there is one used chamber, two exposures
    # and a mandatory terminal clean (H=2). The four DD pair labels and the
    # two chamber names can be permuted; physical identities are left free.
    cfg=x.cfg
    assert x.N==2 and cfg.dummy_count==4 and cfg.cleaning_interval==2
    assert all(w.mode=='2x2' for w in x.products) and len(x.groups)==1 and set(x.groups[0].chambers)==set(cfg.chambers)
    assert expression_value(x,warm,x.pair.product[0,1])>.5
    groups=(x.pair.active,x.pair.product,x.cy.kind,x.cy.occupancy,x.front)
    for group in groups:
        for var in group.values():
            if isinstance(var,(int,float)):continue
            value=round(expression_value(x,warm,var))
            x.model.addCons(var==value)

def trials(case):
    if case=='n2':
        return [('pp_B331','B',331,'pp'),('pp_Bunlimited','B',None,'pp'),('pp_A','A',None,'pp'),
                ('full_B','B',None,'full'),('full_AatB','A','bestB','full')]
    return [('full_B541','B',541,'full'),('full_B','B',None,'full'),('full_AatB','A','bestB','full')]

def solve(case,data,out,seconds):
    meta=read(data/'slices.json')
    for filename,h in meta['backend_hashes'].items():
        from slices import BACKEND
        if digest(BACKEND/filename)!=h:raise ValueError(filename)
    cfg=Config(**meta['config'])
    pool=read_candidates(data,meta)
    audit=Integrated(cfg)
    results=[]
    for i,(tag,goal,cap,family) in enumerate(trials(case)):
        if cap=='bestB':cap=min(p[1] for p in pool)
        x=Integrated(cfg);m=x.model
        if x.bounded:raise ValueError('Bounded input')
        candidates=[p for p in pool if cap is None or p[0 if goal=='B' else 1]<=cap+1e-6]
        source=min(candidates,key=(lambda p:(p[1],p[0])) if goal=='B' else (lambda p:(p[0],p[1])))
        if family=='pp' and source[2]['pj_product_0_1']<.5:
            source=min((p for p in candidates if p[2]['pj_product_0_1']>.5),key=lambda p:p[1] if goal=='B' else p[0])
        warm=set_assignment(x,source[2])
        if family=='pp':pair_family(x,warm)
        if cap is not None:m.addCons((x.cmax if goal=='B' else x.secondary_objective)<=cap+1e-7)
        m.setObjective(x.secondary_objective if goal=='B' else x.cmax,'minimize')
        assert m.checkSol(warm,printreason=True,completely=True,original=True)
        m.addSol(warm)
        m.setRealParam('limits/time',seconds);m.setRealParam('limits/gap',0.0)
        m.setRealParam('limits/memory',3500);m.setIntParam('parallel/maxnthreads',1)
        m.setIntParam('randomization/randomseedshift',1)
        m.setLogfile(str(out/(tag+'.log')))
        log(out,f'{case} {tag} start {source[:2]}, scope={family}, objective={goal}, cap={cap}, nominal budget={seconds}s')
        with progress(out,tag,i,len(trials(case)),seconds):m.optimize()
        best=m.getBestSol()
        vals={v.name:m.getSolVal(best,v) for v in m.getVars(transformed=False)}
        metrics,schedule=physically_checked(audit,vals)
        ab=(metrics['cmax'],metrics['secondary'])
        assert cap is None or ab[0 if goal=='B' else 1]<=cap+TOL
        bound=m.getDualbound()
        row=dict(tag=tag,goal=goal,opposite_cap=cap,scope=family,status=str(m.getStatus()),
                 upper=m.getObjVal(),lower=bound if abs(bound)<1e19 else None,metrics=metrics,
                 nodes=m.getNNodes(),seconds=m.getSolvingTime(),valid_original=True,valid_physical=True)
        if row['lower'] is not None and row['lower']>ab[1 if goal=='B' else 0]+TOL:raise ValueError(row)
        pool.append((ab[0],ab[1],vals))
        np.savez_compressed(out/(tag+'.npz'),v=np.array([vals[n] for n in meta['variables']]))
        save(out/(tag+'_schedule.json'),schedule)
        results.append(row);save(out/'probes.json',results)
        log(out,f'{case} {tag} completed={i+1}/{len(trials(case))} failed=0 status={row["status"]} bound={row["lower"]} verified={ab}')
        m.freeProb()
    audit.model.freeProb()
    save(out/'done.json',dict(completed=len(results),failed=0,solver_seconds=seconds,threads_per_process=1,script_sha256=digest(__file__)))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('case',choices=['n2','n4']);p.add_argument('source',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--seconds',type=float,default=55)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    try:solve(args.case,args.source,args.out,args.seconds)
    except BaseException:
        log(args.out,traceback.format_exc());raise

