"""Time fixed exposure chains with physical routes; certify the constructed schedule on native rows."""
import argparse
import hashlib
import itertools
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ortools.sat.python import cp_model

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
OUT=JMS/'results'/HERE.name
sys.path.insert(0,str(HERE.parent/'table3_mixed16_20261125'))
from prepare import cell,configuration,normalize_schedule,read,sha,sparse_witness,store_primary,validate
from decoder import OrderPattern
from timing import BatchTiming
from patterns import travel
from grippers import attach_hands
sys.path.insert(0,str(HERE.parent/'huber_residence_20261125'))
from score import metrics,physical_lower,final_wafers


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2),encoding='utf8')
    os.replace(tmp,path)


class Block(OrderPattern):
    def make_pairs(self,_):
        return self.product_pairs
    def earliest(self):
        return [0]*len(self.actions)
    def order_robot(self,*args):
        pass


def block(cfg,mode,c,groups):
    return Block(cfg,mode,c,[list(g) for g in groups],{})


def design(cfg):
    one=list(cfg.pjobs[0]['wafers'])
    two=list(cfg.pjobs[1]['wafers'])
    # Consecutive pairs remain FIFO-compatible across all four LPs.
    ds=[f'D{i}' for i in range(1,9)]
    clean=lambda c:block(cfg,'clean',c,[ds[:2],ds[2:4]])
    ans=[]
    for i in range(0,8,2):
        ans.append(block(cfg,'4x1',3,[ds[:2],one[i:i+2]]))
        if i==4 and cfg.cleaning_interval==3:ans.append(clean(3))
    layout=[[2,2,2,1,1]] if cfg.cleaning_interval==10 else [[2,1],[2,1],[1,1]]
    k=0
    for sizes in layout:
        prod=[]
        for j,num in enumerate(sizes):
            group=two[k:k+num];k+=num
            prod.append(group if num==2 else group+[ds[2+j%3]])
        ans.append(block(cfg,'2x2',2,[ds[:2],*prod,ds[4:6]]))
        if cfg.cleaning_interval==3:ans.append(clean(2))
    return ans


def time_blocks(cfg,blocks,scale=16,ideal=True,seed=1,budget=45,hint_times=None,incumbent=None,progress=None,
                specialize=None,workers=1,first=False):
    m=cp_model.CpModel()
    horizon=(4500 if len(blocks)>1 else 1800)*scale
    def var(label=''):
        return m.new_int_var(0,horizon,label)
    actions=[];vs=[];pieces=[];rsc={};tags={};scaled=[]
    def diff(j,i,dt):m.add(vs[j]>=vs[i]+round(scale*dt))
    def interval(i,j,tail,cap):
        length=var()
        rsc.setdefault(cap,[]).append(m.new_interval_var(vs[i],length,vs[j]+int(scale*tail),''))
    nend=final_wafers(8,cfg.cleaning_interval)
    a=(8-nend)/16
    by_ch={};returns=[];picks={};limits=[]
    for p in blocks:
        off=len(actions);pieces.append((p,off));actions.extend(p.actions)
        vs.extend(var() for _ in p.actions)
        def pair(k):return p.handling[k,'pair_load']+off,p.handling[k,'pair_unload']+off
        for q,i in enumerate(p.chamber_ops):
            if q:diff(off+i,off+p.chamber_ops[q-1],p.actions[p.chamber_ops[q-1]].duration)
        if p.chamber in by_ch:
            i=by_ch[p.chamber];diff(off+p.chamber_ops[0],i,actions[i].duration)
        by_ch[p.chamber]=off+p.chamber_ops[-1]
        for expo,back,front in p.cycles:
            m.add(vs[off+expo]==vs[pair(front)[0]]+scale)
        if len(blocks)==1 and ideal and p.mode=='2x2':
            origin=180
            last=len(p.cycles)-1
            # Set successive front exposures at the cadence that gives each
            # nonterminal pair 7-a seconds of residence. The last transition
            # uses the shortest 94 s interval to attain 7 s at the rear exit.
            for q,(expo,_,_) in enumerate(p.cycles):
                t=origin+min(q,last-1)*(95-a)+(94 if q==last else 0)
                m.add(vs[off+expo]==round(scale*t))
            m.add(vs[pair(0)[0]]==round(scale*(origin-10)))
            m.add(vs[pair(0)[1]]==round(scale*(origin+92)))
            m.add(vs[pair(len(p.members)-1)[1]]==vs[off+p.cycles[-1][0]]+90*scale)
        for i,group in enumerate(p.members):
            ld,ul=pair(i)
            duration=sum(1 for _,b,f in p.cycles if i in (b,f))*({'4x1':180,'2x2':90,'clean':500}[p.mode])
            m.add(vs[ul]-vs[ld]-scale<=(duration+100)*scale)
            for r,w in enumerate(group):
                route={k:v+off for k,v in p.routes[2*i+r].items()}
                for k,v in route.items():tags[v]=(ld,k)
                sp,dp=route['source_pick'],route['destination_put']
                diff(ld,sp,3);diff(dp,ul,3)
                m.add(vs[ld]-vs[sp]<=99*scale);m.add(vs[dp]-vs[ul]<=99*scale)
                for a0,b0,allowed in ((sp,ld,range(2)),(ul,dp,range(2,4))):
                    if w.startswith('D'):allowed=range(4)
                    flags=[]
                    for hand in allowed:
                        active=m.new_bool_var('');flags.append(active)
                        slot=m.new_optional_interval_var(vs[a0],var(),vs[b0]+scale,active,'')
                        rsc.setdefault(f'hand{hand}',[]).append(slot)
                    m.add_exactly_one(flags)
                if w.startswith('D'):
                    interval(sp,dp,1,w)
                    continue
                op,al,ap,up,lp,ed=(route[k] for k in ('origin_pick','al_put','al_pick','upper_put','lower_pick','origin_put'))
                for j,i0,lag in ((al,op,7),(ap,al,24),(up,ap,7),(sp,up,34),(lp,dp,26),(ed,lp,7)):
                    diff(j,i0,lag)
                for i0,j,hi in ((op,al,96),(ap,up,96),(lp,ed,96),(al,ap,104),(up,sp,104),(dp,lp,101)):
                    m.add(vs[j]-vs[i0]<=hi*scale)
                interval(op,al,4,'ATR');interval(ap,up,4,'ATR');interval(lp,ed,4,'ATR')
                interval(al,ap,4,'AL');interval(up,sp,31,'U');interval(dp,lp,29,'L')
                returns.append(ed);picks[w]=op
                if ideal:
                    rt=0 if p.mode=='4x1' else 7 if i==len(p.members)-2 else 7-a
                    m.add(vs[ul]-vs[ld]==int(scale*(1+duration+rt)))
    for job in cfg.pjobs:
        nums=[picks[w] for w in job['wafers'] if w in picks]
        for i,j in itertools.pairwise(nums):diff(j,i,0)
    for name,ints in rsc.items():
        m.add_cumulative(ints,[1]*len(ints),2 if name in ('Vin','Vout','U','L','ATR') else 1)
    for i,left in enumerate(actions):
        if not left.robot:continue
        for j in range(i):
            right=actions[j]
            if left.robot!=right.robot:continue
            before=m.new_bool_var('')
            same=(tags.get(i)==tags.get(j) and i in tags and j in tags and left.location==right.location and left.kind not in ('al_put','al_pick'))
            both=[]
            if same:
                sync=m.new_bool_var('');m.add(vs[i]==vs[j]).only_enforce_if(sync);both=[~sync]
            ab=left.duration+travel(cfg,left.robot,left.location,right.location,right.kind)
            ba=right.duration+travel(cfg,right.robot,right.location,left.location,left.kind)
            m.add(vs[j]>=vs[i]+int(scale*ab)).only_enforce_if([before,*both])
            m.add(vs[i]>=vs[j]+int(scale*ba)).only_enforce_if([~before,*both])
    end=var('C')
    if returns:
        m.add_max_equality(end,[vs[i]+4*scale for i in returns])
    else:
        m.add_max_equality(end,[vs[i]+int(actions[i].duration*scale) for i in range(len(vs))])
    if incumbent is not None:m.add(end<=round(scale*incumbent))
    m.minimize(end)
    if specialize:specialize(m,vs,pieces,end)
    if hint_times:
        for v,t in zip(vs,hint_times):m.add_hint(v,round(scale*t))
    solver=cp_model.CpSolver()
    solver.parameters.random_seed=seed;solver.parameters.num_workers=workers;solver.parameters.max_time_in_seconds=budget
    if first:solver.parameters.stop_after_first_solution=True
    if len(blocks)==1 and ideal and blocks[0].mode=='2x2':
        solver.parameters.num_workers=4
        solver.parameters.stop_after_first_solution=True
    class Notify(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            if progress:progress([self.value(v)/scale for v in vs],self.value(end)/scale)
    status=solver.solve(m,Notify())
    if status not in (cp_model.FEASIBLE,cp_model.OPTIMAL):
        raise RuntimeError(f"{solver.status_name(status)} for {[(p.mode,p.members) for p in blocks]}")
    return [solver.value(v)/scale for v in vs],pieces


def validate_native(cfg,doc,folder,meta):
    f=metrics(doc);initial=validate(doc)
    assert initial['valid'],initial['errors'][:5]
    original=cell.lift(cfg,sparse_witness(cfg,doc),None,rebuild=True)
    if not original:raise ValueError('Native model rejected witness')
    store_primary(folder,original,meta)
    replay=read(folder/'primary.json')
    final=metrics(read(folder/'schedule.json'))
    assert all(abs(f[k]-final[k])<2e-5 for k in f)
    return final,replay


def free(h):
    cfg=replace(configuration(),cleaning_interval=h)
    blocks=design(cfg);out=OUT/f'H{h}'/'free';out.mkdir(parents=True,exist_ok=True)
    if (out/'result.json').is_file():
        r=read(out/'result.json')
        assert r['schedule_sha256']==sha(out/'schedule.json')
        return
    shift=0;times=[];pieces=[];start=time.time()
    for i,p in enumerate(blocks):
        file=out/f'block_{i}.json'
        signature=['native-route-block-v1',h,p.mode,p.chamber,p.members]
        if file.exists():
            record=read(file);assert record['signature'][1:]==signature[1:]
            applied=record['times']
        else:
            applied,_=time_blocks(cfg,[p])
            write(file,dict(signature=signature,times=applied))
        pieces.append((p,len(times)));times.extend(t+shift for t in applied)
        shift+=max(t+act.duration for t,act in zip(applied,p.actions))+110
        print(f'H={h}, completed {i+1}/{len(blocks)} isolated blocks, 0 failed, elapsed {time.time()-start:.1f}s',flush=True)
    batch=SimpleNamespace(cfg=cfg,blocks=pieces)
    def reassign(c,data):
        result=normalize_schedule(c,data)
        assert attach_hands(result)
        return result
    with patch('timing.normalize_schedule',reassign):
        doc=BatchTiming.schedule(batch,times)
    target=physical_lower(cfg)
    score=metrics(doc)
    assert abs(score['secondary']-target)<1e-7,score
    f,r=validate_native(cfg,doc,out,dict(analytical_lower=target,terminal_products=final_wafers(8,h)))
    write(out/'result.json',dict(upper=f['secondary'],lower=target,scope='global, free structure, unrestricted product makespan',metrics=f,
          H=h,code_sha256=sha(Path(__file__)),rows=r['rows'],replay=r['replay'],
          schedule_sha256=sha(out/'schedule.json'),assignment_sha256=sha(out/'assignment.json.gz')))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('h',type=int);free(p.parse_args().h)
