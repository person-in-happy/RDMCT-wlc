"""Overlap certified chains and reassign dummy identities without increasing their residence score."""
import itertools
import math
import os
import sys
import time
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import patch
from blocks import (OUT,HERE,Path,cp_model,configuration,replace,design,read,write,sha,
                    travel,block,normalize_schedule,attach_hands,BatchTiming,metrics,validate_native,physical_lower)

SCALE=16


def candidates(h,blocks):
    short=[i for i,b in enumerate(blocks) if b.mode=='4x1']
    long=[i for i,b in enumerate(blocks) if b.mode=='2x2']
    clean=next((i for i,b in enumerate(blocks) if b.mode=='clean'),None)
    unique={}
    for positions in itertools.combinations(range(len(short)+len(long)),len(short)):
        sets=set(positions);f=iter(short);d=iter(long);order=[next(f) if i in sets else next(d) for i in range(len(short)+len(long))]
        for assign in itertools.product((0,1),repeat=len(order)-1):
            routes=[[],[]];counts=[0,0];valid=True
            for i,ch in zip(order,(0,*assign)):
                k=len(blocks[i].cycles)
                if counts[ch]+k>h:
                    if counts[ch]!=h:valid=False;break
                    routes[ch].append(clean);counts[ch]=0
                routes[ch].append(i);counts[ch]+=k
            if not valid:continue
            for ch in range(2):
                if counts[ch]==h:routes[ch].append(clean)
            key=tuple(tuple(row) for row in routes)
            if any(None in row for row in key):continue
            if key in unique:continue
            def finish(row):
                t=0;times={}
                for i in row:
                    if i==clean:t+=508
                    else:
                        t+=188 if i in short else (len(blocks[i].cycles)-1)*95+98
                        times[i]=t
                return times
            a,b=map(finish,routes);end={**a,**b}
            # Consecutive Pjob release intervals can overlap the prior chamber's load window.
            score=max(end.values())+sum(max(0,end[i]-end[j]-160) for seq in (short,long) for i,j in itertools.pairwise(seq))
            unique[key]=score
    return [s for s,_ in sorted(unique.items(),key=lambda z:(z[1],z[0]))]


def place(cfg,library,offsets,routes,limit):
    m=cp_model.CpModel();ss=[];groups=[];arrays=[];holding=defaultdict(list);events=[];releases=[];pick={};dummy=[]
    H=6500*SCALE
    def resource(name,s,start,end):
        holding[name].append(m.new_fixed_size_interval_var(s+start,end-start,''))
    for c,route in enumerate(routes,2):
        prev=None
        for idx in route:
            template=library[idx]
            p=block(cfg,template.mode,c,template.members)
            t=offsets[idx];sh=m.new_int_var(0,H,'')
            if prev:
                s,last=prev
                m.add(sh+t[p.chamber_ops[0]]>=s+last)
            prev=sh,t[p.chamber_ops[-1]]+SCALE
            ss.append(sh);groups.append(p);arrays.append(t)
            actions=[(t[i],a) for i,a in enumerate(p.actions) if a.robot]
            events.append(actions)
            for g,labels in enumerate(p.members):
                ld=t[p.handling[g,'pair_load']]
                ul=t[p.handling[g,'pair_unload']]
                for side,label in enumerate(labels):
                    r={k:t[j] for k,j in p.routes[g*2+side].items()}
                    sp,dp=r['source_pick'],r['destination_put']
                    for x,y,allowed in ((sp,ld+SCALE,(0,1)),(ul,dp+SCALE,(2,3))):
                        choices=[]
                        for h in range(4) if label[0]=='D' else allowed:
                            f=m.new_bool_var('');choices.append(f)
                            holding[f'hand{h}'].append(m.new_optional_fixed_size_interval_var(sh+x,y-x,f,''))
                        m.add_exactly_one(choices)
                    if label.startswith('D'):
                        resource('DS',sh,sp,dp+SCALE)
                    else:
                        op,al,ap,up,lp,ed=[r[k] for k in ('origin_pick','al_put','al_pick','upper_put','lower_pick','origin_put')]
                        releases.append(sh+ed+4*SCALE);pick[label]=sh+op
                        for k,a,b in (('ATR',op,al+4*SCALE),('ATR',ap,up+4*SCALE),('ATR',lp,ed+4*SCALE),('U',up,sp+31*SCALE),('L',dp,lp+29*SCALE),('AL',al,ap+4*SCALE)):
                            resource(k,sh,a,b)
    for k,v in holding.items():
        m.add_cumulative(v,[1]*len(v),8 if k=='DS' else 2 if k in ('ATR','U','L') else 1)
    for job in cfg.pjobs:
        for a,b in itertools.pairwise(job['wafers']):m.add(pick[a]<=pick[b])
    for i,a in enumerate(events):
        for j,b in enumerate(events[:i]):
            disallowed=[]
            for ta,aa in a:
                for tb,bb in b:
                    if aa.robot!=bb.robot:continue
                    ab=int(SCALE*(aa.duration+travel(cfg,aa.robot,aa.location,bb.location,bb.kind)))
                    ba=int(SCALE*(bb.duration+travel(cfg,aa.robot,bb.location,aa.location,aa.kind)))
                    # For distinct pairs, only strictly separated operations can share a robot.
                    disallowed.append((tb-ta-ab+1,tb-ta+ba-1))
            domain=cp_model.Domain.from_intervals(disallowed).complement()
            m.add_linear_expression_in_domain(ss[i]-ss[j],domain)
    C=m.new_int_var(0,H,'C');m.add_max_equality(C,releases)
    if limit:m.add(C<round(limit*SCALE))
    m.minimize(C)
    opt=cp_model.CpSolver();opt.parameters.num_workers=1;opt.parameters.max_time_in_seconds=2
    status=opt.solve(m)
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):return None
    starts=[];parts=[]
    for var,p,t in zip(ss,groups,arrays):
        parts.append((p,len(starts)));starts.extend((opt.value(var)+v)/SCALE for v in t)
    def fix(cfg,doc):
        refs={p['id']:p for p in doc['pairs']};available=[-1.]*8
        aux=[j for j in doc['jobs'] if not j['product']]
        for j in sorted(aux,key=lambda j:(j['loan_start'],j['loan_end'],j['name'])):
            h=next(i for i,v in enumerate(available) if v<=j['loan_start'])
            available[h]=j['loan_end'];r=int(j['name'].split('_')[-1]);j['identity']=refs[j['pair']]['members'][r]=f'D{h+1}'
        data=normalize_schedule(cfg,doc);assert attach_hands(data)
        return data
    with patch('timing.normalize_schedule',fix):
        return BatchTiming.schedule(SimpleNamespace(cfg=cfg,blocks=parts),starts)


def run(h):
    cfg=replace(configuration(),cleaning_interval=h);library=design(cfg);folder=OUT/f'H{h}'/'pack';folder.mkdir(exist_ok=True)
    reference=folder.parent/'free';base=read(reference/'result.json')
    assert abs(base['upper']-physical_lower(cfg))<1e-8
    durations=[[round(t*SCALE) for t in read(reference/f'block_{i}.json')['times']] for i in range(len(library))]
    options=candidates(h,library)[:28]
    sig=dict(code=sha(Path(__file__)),input=sha(reference/'result.json'),options=options)
    if (folder/'result.json').exists():return
    statepath=folder/'progress.json'
    state=read(statepath) if statepath.exists() else dict(signature=sha(Path(__file__)),completed=0,C=base['metrics']['cmax'],elapsed_s=0)
    assert state['signature']==sig['code']
    start=time.monotonic();old=state['elapsed_s']
    for i,route in enumerate(options):
        if i<state['completed']:continue
        doc=place(cfg,library,durations,route,state['C'])
        if doc:
            f=metrics(doc);assert abs(f['secondary']-base['upper'])<1e-8
            write(folder/'candidate.json',doc);state.update(C=f['cmax'],source_index=i)
        t=old+time.monotonic()-start
        state.update(completed=i+1,total=len(options),failed=0,elapsed_s=t,remaining_estimate_s=t/(i+1)*(len(options)-i-1))
        write(statepath,state)
        print(f'H{h} packed chains {i+1}/{len(options)}, 0 failed, C={state["C"]}, ETA ~{state["remaining_estimate_s"]:.1f}s',flush=True)
    doc=read(folder/'candidate.json')
    f,r=validate_native(cfg,doc,folder,dict(source=sha(reference/'result.json'),target=base['upper'],route_id=state['source_index']))
    write(folder/'result.json',dict(upper=f['secondary'],lower=base['upper'],metrics=f,H=h,rows=r['rows'],replay=r['replay'],
              schedule_sha256=sha(folder/'schedule.json'),assignment_sha256=sha(folder/'assignment.json.gz'),source_sha256=sha(reference/'result.json'),
              scope='global minimum process score; product-return time of the shortest checked attaining schedule'))


if __name__=='__main__':run(int(sys.argv[1]))
