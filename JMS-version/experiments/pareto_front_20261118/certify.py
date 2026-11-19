"""Check the open gaps between continuous feasible slices, including their intersections."""
from pathlib import Path
import argparse
import itertools
import time
import traceback
from slices import Config, TOL, Projected, digest, log, read, save
from family import build, extend, lift, progress
from probes import set_assignment
from split_oracle import PATTERNS, SplitOracle, ATR
import numpy as np

def frontier_parts(slices,lo,hi,base):
    lines=[(lo,hi,0,base)]
    boundaries={lo,hi}
    for vs in slices:
        for (a,b),(c,d) in zip(vs,vs[1:]):
            if c-a>TOL:
                slope=(d-b)/(c-a);lines.append((a,c,slope,b-a*slope))
        a,b=vs[-1];lines.append((a,hi,0,b))
    lines=[(max(l,lo),min(r,hi),k,c) for l,r,k,c in lines if r>=lo-TOL and l<=hi+TOL]
    for l,r,k,c in lines:boundaries.update((l,r))
    for (l,r,k,c),(v,w,h,d) in itertools.combinations(lines,2):
        if abs(k-h)>1e-9:
            at=(d-c)/(k-h)
            if max(l,v)+1e-6<at<min(r,w)-1e-6:boundaries.add(at)
    knots=sorted({round(a,7) for a in boundaries})
    parts=[]
    for l,r in zip(knots,knots[1:]):
        if r-l<TOL:continue
        mid=(l+r)/2
        k,c=min(((k,c) for a,b,k,c in lines if a-TOL<=mid<=b+TOL),key=lambda kc:kc[0]*mid+kc[1])
        if parts and abs(parts[-1][2]-k)<1e-7 and abs(parts[-1][3]-c)<1e-5:
            parts[-1][1]=r
        else:parts.append([l,r,k,c])
    return parts

def recipe(x,table):
    for k,z in enumerate(table):
        prod=x.jobs[f'prod_{k}_0'];dummy=x.jobs[f'aux_{k}_1']
        for act in ATR:
            e=next(e for e in x.events if e.get('job')==f'prod_{k}_0' and e['kind']==act)
            x.model.addCons(e['s']==z[act])
        for name,job,act in [('ps',prod,'source_pick'),('ds',dummy,'source_pick'),('pv',prod,'destination_put'),('dv',dummy,'destination_put')]:
            x.model.addCons(job[act]['s']==z[name])
        for p,a,b in [(k,'pl','pu'),(2+2*k,'hl','hu'),(3+2*k,'tl','tu')]:
            x.model.addCons(x.load[p]['s']==z[a]);x.model.addCons(x.unload[p]['s']==z[b])
        for p,a,b in [(2+2*k,'hs','hd'),(3+2*k,'ts','td')]:
            for r in (0,1):
                j=x.jobs[f'aux_{p}_{r}']
                x.model.addCons(j['source_pick']['s']==z[a]);x.model.addCons(j['destination_put']['s']==z[b])

def finish_slice(cfg,kind,values,out):
    x=build(cfg,kind);pg=Projected(x)
    disc=np.array([round(values[pg.names[j]]) for j in pg.id])
    pg.setup(disc);vs=pg.front();points=[]
    for i,v in enumerate(vs):
        pair=pg.verify(v);vec=np.empty(len(pg.names));vec[pg.ic],vec[pg.id]=v,disc
        sol=set_assignment(x,dict(zip(pg.names,vec)))
        try:d=extend(cfg,x.result(solution=sol))
        finally:x.model.freeSol(sol)
        metrics,d=lift(cfg,d)
        assert max(abs(pair-[metrics['cmax'],metrics['secondary']]))<TOL
        save(out/f'vertex_{i}.json',d);points.append(pair.tolist())
    x.model.freeProb()
    return points

def direct_slice(cfg,table,out):
    x=build(cfg,'split')
    recipe(x,table);m=x.model
    m.setRealParam('limits/time',12);m.setRealParam('numerics/feastol',1e-7);m.setObjective(0);m.optimize()
    if not m.getNSols():
        m.freeProb();return None
    sol=m.getBestSol();values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
    m.freeProb()
    return finish_slice(cfg,'split',values,out)

def check(cfg,kind,job,out,sec):
    goal=job[0]
    if kind=='pp':
        x=build(cfg,kind);m=x.model
        if goal=='gap':
            d=m.addVar(lb=0,ub=500,name='strict_gap')
            m.addCons(x.cmax+d<=job[1]);m.addCons(x.secondary_objective+d<=job[2]);m.setObjective(d,'maximize')
        else:
            l,r,k,c=job[1:]
            m.addCons(x.cmax>=l);m.addCons(x.cmax<=r);m.setObjective(x.secondary_objective-k*x.cmax,'minimize')
        m.setRealParam('limits/time',sec);m.setRealParam('numerics/feastol',1e-8)
        m.setIntParam('parallel/maxnthreads',1);m.setLogfile(str(out/'pp.log'));m.optimize()
        ub=m.getObjVal() if m.getNSols() else None
        row=dict(status=str(m.getStatus()),value=ub,bound=m.getDualbound())
        ok=row['status']=='infeasible' or (row['bound']<=TOL if goal=='gap' else row['bound']>=job[4]-TOL)
        vs=None
        if not ok and ub is not None and ((goal=='gap' and ub>TOL) or (goal=='line' and ub<job[4]-TOL)):
            sol=m.getBestSol();v={z.name:m.getSolVal(sol,z) for z in m.getVars(transformed=False)}
            vs=finish_slice(cfg,kind,v,out)
        m.freeProb()
        return [row],ok,vs
    acap=job[1] if goal=='gap' else job[2] if goal=='line' else job[1]
    bcap=job[2] if goal in ('A','B','gap') else 376/3
    rows=[];ok=True;vs=None
    for p in PATTERNS:
        model=SplitOracle(cfg,p,min(acap+1e-7,528.00001),min(bcap+1e-7,376/3+.00001))
        if goal=='line' and not model.impossible:model.model.addCons(model.avar>=job[1])
        objective=('line',-job[3],1) if goal=='line' else job
        row=model.solve(objective,sec,out/(p+'.log'));model.model.freeProb()
        row['pattern']=p;rows.append(row)
        infeas=row['status'] in ('infeasible','infeasible_by_precedence')
        if goal in ('gap','line'):
            good=infeas or (row['bound'] is not None and (row['bound']<=TOL if goal=='gap' else row['bound']>=job[4]-TOL))
            ok &= good
            changed='times' in row and (row['value']>TOL if goal=='gap' else row['value']<job[4]-TOL)
        else:
            ok &= infeas or row['status']=='optimal'
            changed='times' in row
        if changed and vs is None:
            vs=direct_slice(cfg,row['times'],out)
            if vs is None:row['physical_completion']='unverified'
    return rows,ok,vs

def main(kind,source,out,seconds):
    cfg=Config(**read(source/'slices.json')['config'])
    elapsed=time.monotonic()
    initial=read(source/('family_'+kind)/'results.json')
    all_slices=[r['vertices'] for r in initial if 'vertices' in r]
    lo,hi,base=(331.,340.,424/3) if kind=='pp' else (340.,528.,376/3)
    checked={};evaluations=[];attempted=set()
    def execute(job):
        d=out/f'check_{len(evaluations):03}';d.mkdir()
        log(out,f'{kind} query {job} completed={len(evaluations)} failed=0; next proof allocation up to {seconds*(3 if kind=="split" else 1)}s')
        with progress(out,str(job),len(evaluations),len(evaluations)+1,seconds*(3 if kind=='split' else 1)):
            rows,certified,vertices=check(cfg,kind,job,d,seconds)
        record=dict(query=job,details=rows,excluded=certified,vertices=vertices)
        save(d/'evidence.json',record);evaluations.append(record)
        if vertices:all_slices.append(vertices)
        log(out,f'{kind} {job}: bound certified={certified} new slice={vertices} elapsed={time.monotonic()-elapsed:.1f}s')
        return certified
    if kind=='split':
        for job in [('A',528.,42.),('A',528.,376/3)]:
            execute(job)
    for iteration in range(120):
        parts=frontier_parts(all_slices,lo,hi,base);todo=[]
        for l,r,k,c in parts:
            job=('gap',round(r,7),round(c,8)) if abs(k)<1e-8 else ('line',round(l,7),round(r,7),k,c)
            if job not in attempted:todo.append(job)
        if not todo:break
        job=todo[0];attempted.add(job);checked[job]=execute(job)
    else:raise RuntimeError('Interval audit exceeded iteration allocation')
    parts=frontier_parts(all_slices,lo,hi,base)
    intervals=[]
    for l,r,k,c in parts:
        job=('gap',round(r,7),round(c,8)) if abs(k)<1e-8 else ('line',round(l,7),round(r,7),k,c)
        intervals.append(dict(left=l,right=r,slope=k,intercept=c,certified=checked.get(job,False)))
    save(out/'certificate.json',dict(region=[lo,hi],base=base,parts=intervals,slices=all_slices,tests=evaluations,
                             complete=all(s['certified'] for s in intervals),tolerance=TOL,seconds=time.monotonic()-elapsed,
                             files={p:digest(Path(__file__).with_name(p)) for p in ['slices.py','family.py','certify.py','split_oracle.py']}))
    log(out,f'{kind} finished {len(evaluations)} queries, {sum(s["certified"] for s in intervals)}/{len(intervals)} final intervals certified')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['pp','split']);p.add_argument('input',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--seconds',type=float,default=20)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    try:main(a.kind,a.input,a.out,a.seconds)
    except BaseException:log(a.out,traceback.format_exc());raise

