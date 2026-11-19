"""Search four representative mixed-recipe topologies and replay every candidate."""
from dataclasses import replace
from pathlib import Path
import argparse
import traceback
from slices import Config, Integrated, TOL, log, physical_metrics, read, save, validate
from family import fixed,lift
from probes import progress,set_assignment

def model_for(cfg,d4,d2):
    map_prod=[];ch={}
    def prod(lps):
        p=len(map_prod);map_prod.append(lps);return p
    if d4:a,b=prod([1]),prod([2]);four=(a,b)
    else:a=prod([1,2]);four=(4,a)
    if d2:c,d=prod([3]),prod([4])
    else:c=prod([3,4])
    begin=4 if d4 else 5
    pairs_2=[(begin,c),(c,d),(d,begin+1)] if d2 else [(begin,c),(c,begin+1)]
    P=begin+2;Q=len(pairs_2)
    x=Integrated(replace(cfg,max_pairs=P,max_cycles=Q))
    m=x.model;g={v.load_port:v.identifier for v in x.groups}
    for p in range(P):
        on=p<len(map_prod) or p>=4;fixed(m,x.pair.active[p],int(on))
        if p<len(map_prod):
            fixed(m,x.pair.product[p,1],int(len(map_prod[p])==2))
            for r,lp in enumerate(map_prod[p]):fixed(m,x.pair.member[g[lp],p,r],1)
    used=0
    for p in range(P):
        for r in range(2):
            if (p<len(map_prod) and r>=len(map_prod[p])) or p>=4:
                used+=1;fixed(m,x.pair.dummy_identity[f'D{used}',p,r],1)
        if p>=4:
            for k in ['source_pick','destination_put']:
                m.addCons(x.jobs[f'aux_{p}_0'][k]['s']==x.jobs[f'aux_{p}_1'][k]['s'])
    blocks={2:[four],3:pairs_2}
    for chamber,rows in blocks.items():
        for q in range(Q):
            row=rows[q] if q<len(rows) else ()
            for mode in ('4x1','2x2','clean'):
                fixed(m,x.cy.kind[chamber,q,mode],int(bool(row) and mode==('4x1' if chamber==2 else '2x2')))
            for p in range(P):
                fixed(m,x.cy.occupancy[p,chamber,q],int(p in row));fixed(m,x.front[p,chamber,q],int(bool(row) and row[-1]==p))
    m.addCons(x.cmax<=650)
    for v in m.getVars(transformed=False):
        if v.vtype()=='CONTINUOUS':m.chgVarUb(v,min(v.getUbOriginal(),850))
    return x

def run(source,out):
    cfg=Config(**read(source/'slices.json')['config']);allrows=[]
    for i,(d4,d2) in enumerate([(False,False),(True,False),(False,True),(True,True)]):
        name=('PD' if d4 else 'PP')+'_'+('PD' if d2 else 'PP')
        x=model_for(cfg,d4,d2);m=x.model;m.setIntParam('parallel/maxnthreads',1)
        m.setRealParam('limits/time',22);m.setRealParam('numerics/feastol',1e-8)
        for j,goal in enumerate(('A','B')):
            tag=name+'_'+goal
            m.setLogfile(str(out/(tag+'.log')))
            m.setObjective(x.cmax if goal=='A' else x.secondary_objective,'minimize')
            log(out,f'{tag} completed={2*i+j}/8 failed=0 remaining nominal seconds={(8-2*i-j)*22}')
            with progress(out,tag,2*i+j,8,22):m.optimize()
            record=dict(topology=name,goal=goal,status=str(m.getStatus()),bound=m.getDualbound())
            if m.getNSols():
                s=m.getBestSol();vals={v.name:m.getSolVal(s,v) for v in m.getVars(transformed=False)}
                d=x.result(solution=s);ck=validate(d)
                if not ck['valid']:raise ValueError(ck)
                metrics,d=lift(cfg,d);save(out/(tag+'_schedule.json'),d);record['metrics']=metrics
            allrows.append(record);save(out/'results.json',allrows);log(out,str(record))
            if goal=='A':
                if 'metrics' not in record:break
                m.freeTransform();m.addCons(x.cmax<=metrics['cmax']+1e-7)
                s=set_assignment(x,vals)
                if m.checkSol(s,completely=True,original=True):m.addSol(s)
                else:m.freeSol(s)
        m.freeProb()
    log(out,'Topology searches complete')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    try:run(a.source,a.out)
    except BaseException:log(a.out,traceback.format_exc());raise

