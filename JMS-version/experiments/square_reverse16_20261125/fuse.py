"""Fuse two physically observed 2x2 chains and optimize their common transport resources."""
from move import *
from functools import partial
CASES=[
 ('fusionA',-135,35,0),('fusionB',-170,45,0),('fusionC',-150,57,24),('fusionD',-185,55,-10),
]
SECONDS=38

def fuse(fraction=7/16,mode_shift=-150,dual_shift=0):
    cfg=b.configuration();items=dissect(cfg,R/'pareto_scales_20261125/two_blocks/schedule.json')
    full=sorted([(p,t) for p,t in items if p.mode=='4x1'],key=lambda x:x[1][x[0].cycles[0][0]])
    a,c=[x for x in items if x[0].mode=='2x2']
    a,at=a;c,ct=c
    offset=at[a.cycles[-1][0]]-ct[c.cycles[0][0]]
    groups= a.members[:-1]+c.members[1:]
    # All dummy loans are later colored independently against the common inventory of eight.
    dummy=100
    def newblock(p,labels):
        nonlocal dummy
        new=[]
        for row in labels:
            t=[]
            for w in row:
                if w.startswith('D'):dummy+=1;w=f'D{dummy}'
                t.append(w)
            new.append(t)
        return b.block(cfg,p.mode,p.chamber,new)
    p=newblock(a,groups);ts=[]
    ar={(v.kind,v.owner):at[i] for i,v in enumerate(a.actions)}
    cr={(v.kind,v.owner):ct[i]+offset for i,v in enumerate(c.actions)}
    for v in p.actions:
        if v.kind in ('exposure','rot_before','rot_after'):
            turn=v.owner
            if turn<3:d=ar;own=turn
            else:d=cr;own=turn-3
        elif v.kind in ('pair_load','pair_unload'):
            if v.owner<4:d=ar;own=v.owner
            else:d=cr;own=v.owner-3
        else:
            if v.owner//2<4:d=ar;own=v.owner
            else:d=cr;own=v.owner-6
        ts.append(d[v.kind,own]+dual_shift)
    pats=[newblock(f,f.members) for f,s in full]+[p]
    starts=[[v+(mode_shift if i>=2 else 0) for v in w] for i,(f,w) in enumerate(full)]+[ts]
    return cfg,pats,starts

def restrict(radius,m,vs,pieces,end,sources):
    holds=[];sc=16
    for (p,off),src in zip(pieces,sources):
        for i,v in enumerate(p.actions):
            dom=radius if v.kind in ('exposure','pair_load','pair_unload') else radius+25
            m.add_linear_constraint(vs[off+i],max(0,round((src[i]-dom)*sc)),round((src[i]+dom)*sc))
        for g,members in enumerate(p.members):
            for j,w in enumerate(members):
                if w.startswith('D'):
                    r=p.routes[2*g+j];size=m.new_int_var(0,80000,'')
                    holds.append(m.new_interval_var(vs[off+r['source_pick']],size,vs[off+r['destination_put']]+16,''))
            r0,r1=[p.routes[2*g+j] for j in range(2)]
            for k in set(r0)&set(r1):
                if abs(src[r0[k]]-src[r1[k]])<.000001:
                    m.add(vs[off+r0[k]]==vs[off+r1[k]])
    m.add_cumulative(holds,[1]*len(holds),8)

def run_fusion(task):
    name,shift,radius,shiftD=task;cfg,pats,src=fuse(mode_shift=shift,dual_shift=shiftD)
    f=OUT/name;f.mkdir(exist_ok=True);status=f/'progress.json';last=f/'candidate.json';done=f/'done.json'
    identity=dict(source=b.sha(Path(__file__)),input=b.sha(R/'pareto_scales_20261125/two_blocks/schedule.json'),task=list(task))
    r=b.read(status) if status.exists() else dict(identity=identity,elapsed=0,best=None)
    assert identity==r['identity']
    if done.exists():return
    start=time.monotonic();prior=r['elapsed'];stop=threading.Event()
    def update():r['elapsed']=prior+time.monotonic()-start;put(status,r)
    def beat():
        while not stop.wait(2):update()
    th=threading.Thread(target=beat,daemon=True);th.start()
    def cb(ts,c):
        if r['best'] is None or c<r['best']-.00001:
            put(last,dict(times=ts,fA=c));r['best']=c;update();print(name,'C',c,flush=True)
    try:
        b.time_blocks(cfg,pats,scale=16,ideal=True,seed=radius,workers=2,budget=max(.1,SECONDS-prior),
            progress=cb,incumbent=r['best'] or 1140,hint_times=b.read(last)['times'] if last.exists() else [max(t,0) for s in src for t in s],
            specialize=lambda m,vs,p,e:restrict(radius,m,vs,p,e,src))
        r['state']='feasible'
    except RuntimeError as exc:r['state']=str(exc).split(' for ')[0]
    finally:stop.set();th.join();update()
    if last.exists():
        with LOCK:doc=flex_decode(cfg,pats,b.read(last)['times'])
        put(f/'schedule.json',doc);r['metrics']=score.metrics(doc)
    put(done,r)
def main():
    lk=(OUT/'fusion.lock').open('a+b')
    try:msvcrt.locking(lk.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as ex:
        fs=[ex.submit(run_fusion,t) for t in CASES]
        while any(not f.done() for f in fs):
            done=sum((OUT/t[0]/'done.json').exists() for t in CASES);failure=sum(f.done() and f.exception() is not None for f in fs)
            left=sum(0 if(OUT/t[0]/'done.json').exists() else max(0,SECONDS-(b.read(OUT/t[0]/'progress.json')['elapsed'] if(OUT/t[0]/'progress.json').exists() else 0)) for t in CASES)/2
            dt=time.monotonic()-start
            put(OUT/'fusion_progress.json',dict(completed=done,failed=failure,total=len(CASES),elapsed=dt,estimated_total=dt+left,remaining=left,basis='2x2 CP-SAT workers, cumulative per-case budget 38s'))
            print(done,'/',len(CASES),'failed',failure,'elapsed',round(dt),'remaining',round(left),flush=True);time.sleep(3)
        for f in fs:f.result()
    put(OUT/'fusion_progress.json',dict(completed=len(CASES),failed=0,total=len(CASES),elapsed=time.monotonic()-start,remaining=0))
if __name__=='__main__':main()
