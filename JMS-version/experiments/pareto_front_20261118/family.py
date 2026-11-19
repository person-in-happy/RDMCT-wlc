"""S1 productive-phase relaxations with reconstruction in the original model."""
import argparse
import copy
from dataclasses import asdict, replace
from pathlib import Path
import time
import traceback
from slices import Config, Integrated, Projected, TOL, digest, log, np, physical_metrics, read, save, validate
from probes import physically_checked, progress
from seed import constrain_seed, normalize_schedule
from grippers import attach_hands

def fixed(m,var,value):
    if isinstance(var,(int,float)):
        assert var==value
    else:
        m.addCons(var==value)

def build(cfg,kind,limit=630):
    assert cfg.cleaning_interval==2 and cfg.dummy_count==4 and cfg.mix_time==90
    assert cfg.chambers in ([2,3],(2,3)) and len(cfg.pjobs)==1 and cfg.source=='dual'
    assert cfg.max_pairs==cfg.max_cycles==0 and len(cfg.pjobs[0]['wafers'])==2
    assert cfg.pjobs[0]['mode']=='2x2' and set(cfg.pjobs[0]['chambers'])=={2,3}
    num=1 if kind=='pp' else 2
    x=Integrated(replace(cfg,cleaning_interval=3,max_pairs=2+2*num,max_cycles=2))
    m=x.model
    blocks={2+k:(k,2+2*k,3+2*k) for k in range(num)}
    active=set(p for b in blocks.values() for p in b)
    for p in range(x.P):
        fixed(m,x.pair.active[p],int(p in active))
        if p<2:fixed(m,x.pair.product[p,1],int(kind=='pp' and p==0))
        if p>=2:
            for action in ('source_pick','destination_put'):
                a=f'aux_{p}_0_{action}';b=f'aux_{p}_1_{action}'
                ea=next(e for e in x.events if e['name']==a);eb=next(e for e in x.events if e['name']==b)
                m.addCons(ea['s']==eb['s'])
    for c in cfg.chambers:
        for q in range(2):
            if c in blocks:
                p,head,tail=blocks[c];pair=(head,p) if q==0 else (p,tail)
            else:pair=()
            for mode in ('2x2','clean'):fixed(m,x.cy.kind[c,q,mode],int(bool(pair) and mode=='2x2'))
            for p in range(x.P):
                fixed(m,x.cy.occupancy[p,c,q],int(p in pair))
                fixed(m,x.front[p,c,q],int(bool(pair) and p==pair[-1]))
    if kind=='pp':
        for p,ids in [(2,['D1','D2']),(3,['D3','D4'])]:
            for r,t in enumerate(ids):fixed(m,x.pair.dummy_identity[t,p,r],1)
        j0,j1=x.jobs['prod_0_0'],x.jobs['prod_0_1']
        m.addCons(j0['al_put']['s']<=j1['al_put']['s'])
        m.addCons(x.secondary_objective>=28+10*28/3)
    else:
        m.addCons(x.cy.start[2,0]<=x.cy.start[3,0])
        for i in range(2):
            for j in range(2):
                order=m.addVar(vtype='B',name=f'blocks_before_{i}_{j}')
                m.addCons(x.cy.start[3,j]>=x.cy.end[2,i]-800*(1-order))
                m.addCons(x.cy.start[2,i]>=x.cy.end[3,j]-800*order)
        m.addCons(x.secondary_objective>=42);m.addCons(x.cmax>=476)
    m.addCons(x.cmax<=limit)
    # All productive actions of a nondominated schedule here finish by 630+100;
    # each load-lock reset requires at most 30 more seconds. Original big M stays intact.
    for v in m.getVars(transformed=False):
        if v.vtype()=='CONTINUOUS':m.chgVarUb(v,min(v.getUbOriginal(),800.))
    return x

def extend(cfg,d):
    d=copy.deepcopy(d);d['config']=asdict(cfg)
    for c in sorted({cycle['chamber'] for cycle in d['cycles']}):
        t=1200+650*(c-2);ids=[]
        for r,(load,unload,dummies) in enumerate([(t+10,t+535,['D1','D2']),(t+25,t+526,['D3','D4'])]):
            p=max(g['id'] for g in d['pairs'])+1;ids.append(p)
            d['pairs'].append(dict(id=p,chamber=c,mode='clean',members=dummies))
            for kind,z in [('load',load),('unload',unload)]:
                d['events'].append(dict(name=f'{kind}_{p}',kind='pair_'+kind,robot='VTR',location=f'CH{c}',start=z,end=z+1,pair=p))
            for i,w in enumerate(dummies):
                name=f'aux_{p}_{i}'
                for act,z in [('source_pick',load-3),('destination_put',unload+3)]:
                    d['events'].append(dict(name=name+'_'+act,kind=act,robot='VTR',location='VS',start=z,end=z+1,job=name))
                d['jobs'].append(dict(name=name,identity=w,product=False,pair=p,origin='VS',loan_start=load-3,loan_end=unload+4,
                                      load_start=load,load_end=load+1,unload_start=unload,unload_end=unload+1))
        for side,z in [('before',t+13),('after',t+527)]:
            d['events'].append(dict(name=f'rot_{side}_{c}_2',kind='rotate',robot=None,location=f'CH{c}',start=z,end=z+2,chamber=c,cycle=2))
        d['cycles'].append(dict(chamber=c,index=2,mode='clean',pairs=ids,front=ids[1],start=t+26,end=t+526,counter=0))
    assert attach_hands(d)
    d=normalize_schedule(cfg,d);d['cmax']=max(j['loan_end'] for j in d['jobs'] if j['product'])
    audit=validate(d)
    if not audit['valid']:raise ValueError(audit)
    return d

def lift(cfg,d):
    full=Integrated(cfg);m=full.model;constrain_seed(full,d)
    m.setObjective(0,'minimize');m.setRealParam('limits/time',30)
    m.optimize()
    if not m.getNSols():raise ValueError('Full-model schedule completion: '+str(m.getStatus()))
    sol=m.getBestSol();vals={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
    m.freeProb()
    raw=Integrated(cfg);stats,out=physically_checked(raw,vals);raw.model.freeProb()
    return stats,out

def queries(kind):
    if kind=='pp':return [('A',None),('B',630),('B',331),('B',332),('B',333),('B',334),('B',335),('B',337),('B',340),('B',346),('B',360),('B',379),('A',125.333334)]
    return [('A',42.000001),('A',None),('B',520),('B',540),('B',560),('B',580),('B',600)]

def oracle(cfg,kind,job,out,seconds,progress_counts):
    goal,cap=job
    x=build(cfg,kind);m=x.model
    if cap is not None:
        m.addCons((x.cmax if goal=='B' else x.secondary_objective)<=cap+1e-8)
    m.setObjective(x.cmax if goal=='A' else x.secondary_objective,'minimize')
    m.setIntParam('parallel/maxnthreads',1);m.setRealParam('limits/time',seconds)
    m.setRealParam('numerics/feastol',1e-8);m.setRealParam('limits/memory',3000)
    m.setLogfile(str(out/'solver.log'))
    with progress(out,str(job),*progress_counts,seconds):m.optimize()
    row=dict(goal=goal,cap=cap,status=str(m.getStatus()),bound=m.getDualbound(),seconds=m.getSolvingTime(),nodes=m.getNNodes())
    if abs(row['bound'])>=1e19:row['bound']=None
    if not m.getNSols():m.freeProb();return row
    sol=m.getBestSol()
    d=x.result(solution=sol)
    audit=validate(d)
    if not audit['valid']:raise ValueError(audit)
    vals={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
    row['upper']=m.getObjVal()
    m.freeTransform()
    # Rebuild the bare family, dropping this query's cap before computing its slice.
    hull=build(cfg,kind);pg=Projected(hull)
    disc=np.asarray([round(vals[pg.names[j]]) for j in pg.id],dtype=np.int32)
    pg.setup(disc);vs=pg.front();points=[]
    for i,v in enumerate(vs):
        pair=pg.verify(v);fullvals=np.empty(len(pg.names));fullvals[pg.ic],fullvals[pg.id]=v,disc
        from probes import set_assignment
        ss=set_assignment(hull,dict(zip(pg.names,fullvals)))
        try:d=extend(cfg,hull.result(solution=ss))
        finally:hull.model.freeSol(ss)
        metrics,d=lift(cfg,d)
        assert max(abs(pair-np.array([metrics['cmax'],metrics['secondary']])))<TOL
        points.append(pair.tolist());save(out/f'vertex_{i}.json',d)
    row.update(vertices=points,lp_solves=pg.lps,integer_sha256=hashlib.sha256(disc.astype('<i4').tobytes()).hexdigest())
    m.freeProb();hull.model.freeProb()
    return row

import hashlib
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('kind',choices=['pp','split']);p.add_argument('input',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--seconds',type=float,default=35)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    try:
        cfg=Config(**read(args.input/'slices.json')['config']);records=[]
        tasks=queries(args.kind)
        for i,job in enumerate(tasks):
            dest=args.out/f'q{i:02}';dest.mkdir()
            log(args.out,f'{args.kind} {job} completed={i}/{len(tasks)} failed=0 maximum solver time remaining={(len(tasks)-i)*args.seconds}s')
            row=oracle(cfg,args.kind,job,dest,args.seconds,(i,len(tasks)));records.append(row)
            save(dest/'result.json',row);save(args.out/'results.json',records)
            log(args.out,str(row))
        log(args.out,f'completed={len(tasks)}/{len(tasks)} failed=0')
    except BaseException:
        log(args.out,traceback.format_exc());raise

