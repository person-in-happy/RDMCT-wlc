"""Reach the analytic B endpoint on two physical four-wafer cycle assignments."""
from pathlib import Path
import argparse
import traceback
from slices import Config, Integrated, TOL, np, read, save, log
from probes import physically_checked, progress
from family import fixed

def topology(x,kind):
    m=x.model
    groups={g.load_port:g.identifier for g in x.groups}
    for p in range(4):
        fixed(m,x.pair.member[groups[p+1],p,0],1);fixed(m,x.pair.product[p,1],0)
    if kind=='chain':
        blocks={2:[('4x1',0,1)],3:[('2x2',4,2),('2x2',2,3),('2x2',3,5)]}
        aux={4:('D5','D6'),5:('D7','D8')}
    elif kind=='separate':
        blocks={2:[('4x1',0,1),('2x2',4,2),('2x2',2,5)],3:[('2x2',6,3),('2x2',3,7)]}
        aux={4:('D5','D6'),5:('D5','D6'),6:('D7','D8'),7:('D7','D8')}
    else:raise ValueError(kind)
    active=set(range(4))|set(aux)
    for p in range(x.P):
        fixed(m,x.pair.active[p],int(p in active))
    for p in range(4):fixed(m,x.pair.dummy_identity[f'D{p+1}',p,1],1)
    for p,ids in aux.items():
        for r,t in enumerate(ids):fixed(m,x.pair.dummy_identity[t,p,r],1)
    for c in x.cfg.chambers:
        for q in range(x.Q):
            blk=blocks[c][q] if q<len(blocks[c]) else ('',-1,-1)
            for k in ['4x1','2x2','clean']:fixed(m,x.cy.kind[c,q,k],int(blk[0]==k))
            for p in range(x.P):
                fixed(m,x.cy.occupancy[p,c,q],int(p in blk[1:]));fixed(m,x.front[p,c,q],int(p==blk[2]))
    # All four P+D pairs have one pre-load and one post-unload wait of >=3.
    # Equality B=54 allows no other waiting, and requires zero rhythm deviation.
    for p in range(4):
        pjob=x.jobs[f'prod_{p}_0'];djob=x.jobs[f'aux_{p}_1']
        for j in [pjob]:
            by={e['kind']:e for e in x.events if e.get('job')==j['name']}
            for a,b,d in [('origin_pick','al_put',3),('al_put','al_pick',20),('al_pick','upper_put',3),
                          ('upper_put','source_pick',30),('destination_put','lower_pick',25),('lower_pick','origin_put',3)]:
                m.addCons(by[b]['s']==by[a]['e']+d)
        m.addCons(sum(j['load_s']-j['source_pick']['e']-2 for j in (pjob,djob))==3)
        m.addCons(sum(j['destination_put']['s']-j['unload_e']-2 for j in (pjob,djob))==3)
    for p in aux:
        for r in (0,1):
            j=x.jobs[f'aux_{p}_{r}'];m.addCons(j['load_s']==j['source_pick']['e']+2)
            m.addCons(j['destination_put']['s']==j['unload_e']+2)
    for v in x.rhythm:m.addCons(v==0)
    m.addCons(x.max_wait==3);m.addCons(x.secondary_objective<=54.0000001)

def run(source,out):
    meta=read(source/'slices.json');cfg=Config(**meta['config'])
    rec=[];audit=Integrated(cfg)
    for i,kind in enumerate(['chain','separate']):
        x=Integrated(cfg);m=x.model;topology(x,kind);m.addCons(x.cmax<=1800)
        m.setObjective(x.cmax,'minimize');m.setIntParam('parallel/maxnthreads',1);m.setRealParam('limits/time',45)
        m.setRealParam('numerics/feastol',1e-8);m.setLogfile(str(out/(kind+'.log')))
        log(out,f'{kind}: completed={i}/2, failed=0, remaining nominal seconds={(2-i)*45}')
        with progress(out,kind,i,2,45):m.optimize()
        row=dict(topology=kind,status=str(m.getStatus()),seconds=m.getSolvingTime(),lower_A_given_topology=m.getDualbound())
        if m.getNSols():
            vals={v.name:m.getSolVal(m.getBestSol(),v) for v in m.getVars(transformed=False)}
            metrics,d=physically_checked(audit,vals);assert abs(metrics['secondary']-54)<TOL
            row['metrics']=metrics;save(out/(kind+'_schedule.json'),d)
            np.savez_compressed(out/(kind+'.npz'),v=np.array([vals[n] for n in meta['variables']]))
        rec.append(row);save(out/'results.json',rec);log(out,str(row));m.freeProb()
    audit.model.freeProb();log(out,'completed=2/2 failed=0')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    try:run(a.source,a.out)
    except BaseException:log(a.out,traceback.format_exc());raise

