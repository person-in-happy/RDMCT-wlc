"""Attain the universal B lower bound for the S1 two-product split pairing."""
from dataclasses import asdict
from pathlib import Path
import argparse
import traceback
from slices import Config, Integrated, TOL, log, np, read, save, validate
from probes import physically_checked, progress
from seed import normalize_schedule, constrain_seed
from grippers import attach_hands

def schedule(cfg):
    pairs=[]; cycles=[]; jobs=[]; events=[]
    for k,ch in enumerate(cfg.chambers):
        product=f'LP1_W{k+1}'
        phase=380*k; clean=900+600*k
        def emit(name,kind,robot,loc,t,duration,**items):
            events.append(dict(name=name,kind=kind,robot=robot,location=loc,start=t,end=t+duration,**items))
        def make_pair(members,mode,l,u):
            idx=len(pairs);station=f'CH{ch}'; is_pd=product in members
            pairs.append(dict(id=idx,chamber=ch,mode=mode,members=members))
            for kind,t in [('load',l),('unload',u)]:
                emit(f'{kind}_{idx}',f'pair_{kind}','VTR',station,t,1,pair=idx)
            for r,w in enumerate(members):
                pw=(w==product);name=w if pw else f'aux_{idx}_{r}'
                source='LP1' if pw else 'VS'
                pick=l-(6 if pw else 3)
                put=u+(6 if is_pd and not pw else 3)
                def job_event(kind,robot,loc,t,dt):emit(name+'_'+kind,kind,robot,loc,t,dt,job=name)
                job_event('source_pick','VTR','U' if pw else 'VS',pick,1)
                job_event('destination_put','VTR','L' if pw else 'VS',put,1)
                begin,end=pick,put+1
                if pw:
                    begin=pick-72
                    for kind,loc,when in [('origin_pick','LP1',begin),('al_put','AL',begin+7),
                      ('al_pick','AL',begin+31),('upper_put','U',begin+38),
                      ('lower_pick','L',put+26),('origin_put','LP1',put+33)]:
                        job_event(kind,'ATR',loc,when,4)
                    end=put+37
                jobs.append(dict(name=name,identity=w,product=pw,origin=source,pair=idx,loan_start=begin,loan_end=end,
                                 load_start=l,load_end=l+1,unload_start=u,unload_end=u+1))
            return idx
        p=make_pair([product,'D1'],'2x2',phase+100,phase+303)
        d0=make_pair(['D2','D3'],'2x2',phase+80,phase+194)
        d1=make_pair(['D2','D3'],'2x2',phase+205,phase+296)
        cb=make_pair(['D1','D2'],'clean',clean+10,clean+535)
        cf=make_pair(['D3','D4'],'clean',clean+25,clean+526)
        for q,mode,back,front,t,dt,rb,ra in [
                (0,'2x2',d0,p,phase+101,90,phase+82,None),
                (1,'2x2',p,d1,phase+206,90,phase+191,phase+297),
                (2,'clean',cb,cf,clean+26,500,clean+13,clean+527)]:
            cycles.append(dict(chamber=ch,index=q,mode=mode,pairs=[back,front],front=front,start=t,end=t+dt,counter=q+1 if q<2 else 0))
            emit(f'rot_before_{ch}_{q}','rotate',None,f'CH{ch}',rb,2,chamber=ch,cycle=q)
            if ra is not None:emit(f'rot_after_{ch}_{q}','rotate',None,f'CH{ch}',ra,2,chamber=ch,cycle=q)
    d=dict(schema=1,config=asdict(cfg),solutions=1,events=events,jobs=jobs,pairs=pairs,cycles=cycles,
           cmax=max(j['loan_end'] for j in jobs if j['product']),cleaning_policy='optional_before_threshold')
    assert attach_hands(d)
    d=normalize_schedule(cfg,d)
    check=validate(d)
    if not check['valid']:raise ValueError(check)
    return d

def run(source,out):
    from slices import Projected
    meta=read(source/'slices.json');cfg=Config(**meta['config'])
    d=schedule(cfg)
    x=Integrated(cfg);m=x.model
    constrain_seed(x,d)
    m.setRealParam('limits/time',30);m.setObjective(0,'minimize')
    log(out,'S1 split schedule completion: 0/2, failed=0, ETA up to 30s')
    m.optimize()
    if not m.getNSols():raise ValueError(str(m.getStatus()))
    sol=m.getBestSol();vals={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
    audit=Integrated(cfg)
    metrics,d=physically_checked(audit,vals)
    assert abs(metrics['secondary']-42)<TOL
    save(out/'constructed.json',dict(metrics=metrics,physical=d))
    log(out,'S1 split schedule completion: 1/2, failed=0; tightening all event times on its discrete assignment')
    pg=Projected(audit)
    pg.setup(np.array([round(vals[pg.names[j]]) for j in pg.id]))
    vertices=pg.front()
    points=[pg.verify(v).tolist() for v in vertices]
    for idx,vertex in enumerate(vertices):
        values=np.empty(len(pg.variables));values[pg.ic],values[pg.id]=vertex,pg.discrete
        as_dict=dict(zip(pg.names,values))
        stats,sched=physically_checked(audit,as_dict)
        save(out/f'vertex_{idx}_schedule.json',sched)
        np.savez_compressed(out/f'vertex_{idx}.npz',v=np.asarray([as_dict[n] for n in meta['variables']]))
    save(out/'split.json',dict(constructed=metrics,vertices=points,source='two separately processed product-dummy pairs',original_and_physical_valid=True))
    log(out,f'S1 split completed=2/2 failed=0 verified vertices {points}')
    audit.model.freeProb();m.freeProb()

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('source',type=Path);p.add_argument('out',type=Path)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    try:run(args.source,args.out)
    except BaseException:
        log(args.out,traceback.format_exc());raise

