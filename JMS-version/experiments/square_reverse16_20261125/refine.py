"""Iterated release of robot event order at a fixed, low per-wafer residence profile."""
from move import *
from hashlib import sha256
LIM=24
RANGES=[('steps_narrow',28,22),('steps_wide',49,33)]
def step(task,folder,source,d_num,shift,radius):
    folder.mkdir(parents=True,exist_ok=True);done=folder/'done.json';clk=folder/'progress.json';candidate=folder/'candidate.json'
    identity=dict(source=b.sha(source),code=b.sha(Path(__file__)),task=task,d_num=d_num,shift=shift,radius=radius)
    if done.exists():
        assert b.read(done)['identity']==identity;return
    cfg=b.configuration();old=dissect(cfg,source);pats=[];sources=[];shifts=[]
    aux=100
    for k,(p,ts) in enumerate(old):
        groups=[]
        for labels in p.members:
            out=[]
            for w in labels:
                if w.startswith('D'):aux+=1;w=f'D{aux}'
                out.append(w)
            groups.append(out)
        pats.append(b.block(cfg,p.mode,p.chamber,groups));sources.append(ts)
        e0=ts[p.cycles[0][0]];shifts.append(-shift if e0>250 else 0)
    def restrict(m,vs,pieces,end):
        holds=[]
        for (p,off),ts,sh in zip(pieces,sources,shifts):
            for i,v in enumerate(p.actions):
                tol=radius+(22 if v.robot else 0)
                m.add_linear_constraint(vs[off+i],max(0,round((ts[i]+sh-tol)*16)),round((ts[i]+sh+tol)*16))
            for i,labels in enumerate(p.members):
                l,u=(p.handling[i,k] for k in ('pair_load','pair_unload'))
                for j,w in enumerate(labels):
                    r=p.routes[2*i+j]
                    if w.startswith('D'):
                        z=m.new_int_var(0,80000,'')
                        holds.append(m.new_interval_var(vs[off+r['source_pick']],z,vs[off+r['destination_put']]+16,''))
                if any(w.startswith('LP') for w in labels):
                    rt=0 if p.mode=='4x1' else 7*16 if i==len(p.members)-2 else 7*16-d_num
                    m.add(vs[off+u]-vs[off+l]==181*16+rt)
                a,bb=p.routes[2*i],p.routes[2*i+1]
                for k in set(a)&set(bb):
                    if abs(ts[a[k]]-ts[bb[k]])<.00001:
                        m.add(vs[off+a[k]]==vs[off+bb[k]])
        m.add_cumulative(holds,[1]*len(holds),8)
    rec=b.read(clk) if clk.exists() else dict(identity=identity,best=None,elapsed=0)
    assert rec['identity']==identity
    started=time.monotonic();base=rec['elapsed'];stop=threading.Event()
    def update():
        rec['elapsed']=base+time.monotonic()-started;put(clk,rec)
    def beat():
        while not stop.wait(2):update()
    th=threading.Thread(target=beat,daemon=True);th.start()
    def cb(ts,c):
        if rec['best'] is None or c<rec['best']-.00001:
            put(candidate,dict(fA=c,times=ts));rec['best']=c;update()
    hints=b.read(candidate)['times'] if candidate.exists() else [t for ts in sources for t in ts]
    try:
        b.time_blocks(cfg,pats,scale=16,ideal=False,seed=radius+d_num,budget=max(.1,LIM-base),workers=2,
            progress=cb,incumbent=rec['best'] or b.read(source)['cmax']+1, hint_times=hints,specialize=restrict)
        rec['state']='feasible'
    except RuntimeError as err:rec['state']=str(err).split(' for ')[0]
    finally:stop.set();th.join();update()
    if candidate.exists():
        with LOCK:doc=flex_decode(cfg,pats,b.read(candidate)['times'])
        put(folder/'schedule.json',doc);rec['metrics']=score.metrics(doc)
    put(done,rec)
def flow(arm):
    name,radius,shift=arm;path=OUT/'float_free/native/schedule.json'
    for i in range(3):
        folder=OUT/(name+str(i))
        step(name+str(i),folder,path,7,shift,radius)
        if (folder/'schedule.json').exists() and b.read(folder/'schedule.json')['cmax']<b.read(path)['cmax']-.01:
            path=folder/'schedule.json'
        else:break
    for d in ([6,8] if name.endswith('narrow') else [5,9]):
        folder=OUT/(name+'D'+str(d));step(name+'D'+str(d),folder,path,d,5,12)
def main():
    lk=(OUT/'refine.lock').open('a+b')
    try:msvcrt.locking(lk.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as ex:
        fs=[ex.submit(flow,x) for x in RANGES]
        while any(not f.done() for f in fs):
            done=len(list(OUT.glob('steps*/done.json')))
            bad=sum(f.done() and f.exception() is not None for f in fs);dt=time.monotonic()-start
            left=max(0,(10-done)*LIM/2-sum(b.read(p)['elapsed'] for p in OUT.glob('steps*/progress.json') if not(p.parent/'done.json').exists())/2)
            put(OUT/'refine_progress.json',dict(completed=done,failed=bad,total=10,elapsed=dt,estimated_total=dt+left,remaining=left,basis='up to 3 sequential 24s neighborhoods and 2 profile perturbations per parallel arm; repeated plateau skips future centers'))
            print('Refine',done,'/ up to 10, errors',bad,'elapsed',round(dt),'remaining <=',round(left),flush=True);time.sleep(2)
        for f in fs:f.result()
    put(OUT/'refine_progress.json',dict(completed=len(list(OUT.glob('steps*/done.json'))),failed=0,elapsed=time.monotonic()-start,remaining=0))
if __name__=='__main__':main()
