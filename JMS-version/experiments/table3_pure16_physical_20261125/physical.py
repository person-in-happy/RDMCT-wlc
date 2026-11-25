"""Active-operation integer-time search for 16 single-exposure products and their real support wafers."""
from dataclasses import asdict
from itertools import combinations,product
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'table3_pure16_20261125'))
from common16 import OUT as BASE,JMS,config,setup,load,save,sha
from projection16 import STEPS,DUR,tightened,cp_model
cell=setup()
from grippers import attach_hands
from seed import normalize_schedule
from validate import validate
from witness import sparse_witness
from protocol import save as compressed
CFG=config('4x1')
SOURCE=BASE/'4x1/raw/schedule.json'
DEST=BASE/'4x1/search/compact_active'

def make(source,cap,window):
    doc=load(SOURCE);m=tightened(doc,cap);m.clear_hints()
    vm={v.name:m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables)}
    original=load(source);cfg=CFG
    labels=cfg.pjobs[0]['wafers'];qmax=1+(cap-76-40-180)//188
    events={};cycles=[];pairs=[];jobs=[];ops={'A':[],'V':[]};hands=[];side_ops={}
    def new(k):return m.new_int_var(0,cap+250,k)
    def add(k,kind,location,robot,duration,var=None,hint=None,group=None,**meta):
        v=new(k) if var is None else var
        events[k]=(v,dict(name=k,kind=kind,location=location,robot=robot,**meta),duration)
        if robot in ('ATR','VTR'):
            ops[{'ATR':'A','VTR':'V'}[robot]].append((v,kind,location,duration,hint,group))
        return v
    for key,v in vm.items():
        if key.startswith(('w','use','full')) and (key.startswith('w') and key[1].isdigit() or key.startswith(('use','full'))):
            if key.startswith('full'):continue
            m.add(v==original.get(key,0))
    dummy=0
    for c in range(2):
        prev=None
        for q in range(qmax):
            if not original.get(f'use{c,q}'):continue
            start=vm[f'start{c,q}'];m.add(vm[f'full{c,q}']==1)
            chamber=c+2;loc=f'CH{chamber}';ids=[];side=[]
            for s in (0,1):
                indices=[i for i in range(16) if original.get(f'w{i}_{c}_{q}_{s}')];p=len(pairs);ids.append(p)
                members=list(indices)
                while len(members)<2:dummy+=1;members.append('D'+str(dummy))
                assert dummy<=cfg.dummy_count
                pairs.append(dict(id=p,members=[labels[i] if isinstance(i,int) else i for i in members],chamber=chamber,mode='4x1'))
                l=add(f'load_{p}','pair_load',loc,'VTR',1,vm[f'{indices[0]}_load'] if indices else None,original.get(f'{indices[0]}_load') if indices else None,p,pair=p)
                u=add(f'unload_{p}','pair_unload',loc,'VTR',1,vm[f'{indices[0]}_unload'] if indices else None,original.get(f'{indices[0]}_unload') if indices else None,p,pair=p)
                m.add(u<=l+281);side.append((l,u))
                for r,i in enumerate(members):
                    isprod=isinstance(i,int);identity=labels[i] if isprod else i;origin=identity.split('_')[0] if isprod else 'VS';jname=f'w_{p}_{r}'
                    series={}
                    for name,dur in zip(STEPS,DUR):
                        if name in ('load','unload') or (not isprod and name not in ('source_pick','destination_put')):continue
                        location={'origin_pick':origin,'origin_put':origin,'al_put':'AL','al_pick':'AL','upper_put':'U','lower_pick':'L',
                                  'source_pick':'U' if isprod else 'VS','destination_put':'L' if isprod else 'VS'}[name]
                        robot='VTR' if name in ('source_pick','destination_put') else 'ATR'
                        series[name]=add(jname+'_'+name,name,location,robot,dur,vm[f'{i}_{name}'] if isprod else None,
                                         original.get(f'{i}_{name}',0) if isprod else None,p,job=jname)
                    sp=series['source_pick'];dp=series['destination_put'];m.add(l>=sp+3);m.add(dp>=u+3)
                    m.add(l+1-sp<=100);m.add(dp+1-u<=100)
                    if isprod:
                        for a,b,limit in [('al_put','al_pick',104),('upper_put','source_pick',104),('destination_put','lower_pick',101),
                                         ('origin_pick','al_put',96),('al_pick','upper_put',96),('lower_pick','origin_put',96)]:m.add(series[b]<=series[a]+limit)
                    for a,b,allowed in ((sp,l+1,range(2) if isprod else range(4)),(u,dp+1,range(2,4) if isprod else range(4))):
                        hands.append((a,b,list(allowed)))
                    jobs.append((dict(name=jname,pair=p,identity=identity,product=isprod,origin=origin),series,l,u))
                if not indices:
                    for kind in ('source_pick','destination_put'):m.add(jobs[-1][1][kind]==jobs[-2][1][kind])
            bl,bu=side[0];fl,fu=side[1]
            rb=add(f'rot_before_{chamber}_{q}','rotate',loc,None,2,chamber=chamber,cycle=q)
            ra=add(f'rot_after_{chamber}_{q}','rotate',loc,None,2,chamber=chamber,cycle=q)
            for cond in [rb>=bl+1,fl>=rb+2,start==fl+1,fu>=start+180,ra>=fu+1,bu>=ra+2]:m.add(cond)
            if prev is not None:m.add(bl>=prev+1)
            prev=bu;cycles.append((dict(chamber=chamber,index=q,mode='4x1',counter=q+1,pairs=ids,front=ids[1]),start))
    perhand=[[] for _ in range(4)]
    for idx,(a,b,allowed) in enumerate(hands):
        size=m.new_int_var(1,100,'');m.add(size==b-a);uses=[]
        for h in allowed:
            flag=m.new_bool_var('');uses.append(flag);perhand[h].append(m.new_optional_interval_var(a,size,b,flag,''))
        m.add_exactly_one(uses)
    for segs in perhand:m.add_no_overlap(segs)
    for robot,actions in ops.items():
        for (a,ka,la,da,ha,pa),(b,kb,lb,db,hb,pb) in combinations(actions,2):
            sync=ka==kb and la==lb and pa==pb and ka not in ('al_put','al_pick')
            if sync and ((ha is None and hb is None) or (ha is not None and hb is not None and ha==hb)):
                m.add(a==b);continue
            travel=0 if la==lb or {la,lb}<={'U','L'} else 3 if robot=='A' else 2
            ab=da+(6 if la in ('U','L') and kb=='origin_pick' else travel)
            ba=db+(6 if lb in ('U','L') and ka=='origin_pick' else travel)
            if ha is not None and hb is not None and abs(ha-hb)>window:
                m.add(b>=a+ab if ha<hb else a>=b+ba)
            else:
                order=m.new_bool_var('');m.add(b>=a+ab).only_enforce_if(order);m.add(a>=b+ba).only_enforce_if(order.Not())
                if ha is not None and hb is not None:m.add_hint(order,int(ha<hb))
    for key,val in original.items():
        if key in vm:m.add_hint(vm[key],val)
    def decode(solver):
        val=solver.value
        rows=[dict(meta,start=val(v),end=val(v)+dur) for v,meta,dur in events.values()]
        ww=[]
        for meta,series,l,u in jobs:
            prod=meta['product'];a,b=('origin_pick','origin_put') if prod else ('source_pick','destination_put')
            ww.append(dict(meta,loan_start=val(series[a]),loan_end=val(series[b])+(4 if prod else 1),load_start=val(l),load_end=val(l)+1,unload_start=val(u),unload_end=val(u)+1))
        cy=[dict(meta,start=val(v),end=val(v)+180) for meta,v in cycles]
        data=normalize_schedule(cfg,dict(schema=1,solutions=1,cmax=val(vm['makespan']),jobs=ww,cycles=cy,pairs=pairs,events=rows,config=asdict(cfg)))
        assert attach_hands(data)
        replay=validate(data)
        if not replay['valid']:raise ValueError(replay['errors'][:6])
        return data
    return m,decode

def main(source,cap,window,budget,folder):
    from threading import Event,Thread
    folder.mkdir(exist_ok=True,parents=True); checkpoint=folder/'progress.json'
    ident=dict(source=sha(source),source_file=str(source.relative_to(JMS)),code=sha(Path(__file__)),cap=cap,window=window,budget=budget,threads=1)
    state=load(checkpoint) if checkpoint.exists() else dict(identity=ident,used=0,upper=None)
    assert state['identity']==ident
    if (folder/'result.json').exists():return
    start=time.monotonic();used=state['used'];m,decode=make(source,cap,window)
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=max(.05,budget-used);solver.parameters.log_to_stdout=False
    if state['upper'] is not None:
        v=next(m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables) if v.name=='makespan');m.add(v<state['upper'])
    stop=Event();t0=time.monotonic();errors=[]
    def pulse():
        while not stop.wait(1):
            state['used']=min(budget,used+time.monotonic()-t0);save(checkpoint,state)
    class Callback(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            try:
                data=decode(self);c=data['cmax'];path=folder/f'schedule_{c}.json';save(path,data)
                state['upper']=c
                print(f'Validated {c} s; {time.monotonic()-start:.1f}s elapsed, ~{max(0,budget-used-time.monotonic()+t0):.1f}s remaining',flush=True)
            except Exception as e:
                errors.append(e);self.stop_search()
    th=Thread(target=pulse);th.start()
    try:status=solver.solve(m,Callback())
    finally:stop.set();th.join()
    if errors:raise errors[0]
    state['used']=min(budget,used+time.monotonic()-t0);save(checkpoint,state)
    save(folder/'result.json',dict(state,restricted_status=solver.status_name(status),restricted_bound=solver.best_objective_bound))

if __name__=='__main__':
    main(Path(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),Path(sys.argv[5]))
