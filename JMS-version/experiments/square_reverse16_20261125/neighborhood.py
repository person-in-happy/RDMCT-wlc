"""Local robot-order exchange around unrestricted-low-score native witnesses."""
from reverse import *
from dataclasses import replace
import itertools,json
from collections import defaultdict
R=JMS/'results'
TRIALS=[
 ('two_near','two',50,20),('one_move','one',0,26),
 ('two_mid','two',120,40),('one_early','one',29,45)
]
WALL=38

def dissect(cfg,file):
    s=b.read(file);pairs={p['id']:p for p in s['pairs']};jobs=defaultdict(list)
    events={};je={}
    for j in s['jobs']:jobs[j['pair']].append(j)
    for e in s['events']:
        if 'job'in e:je[e['job'],e['kind']]=e['start']
        events[e['name']]=e['start']
    pieces=[]
    for ch in (2,3):
        cy=[x for x in s['cycles'] if x['chamber']==ch]
        groups=[]
        for c in cy:
            if c['mode']=='2x2' and groups and groups[-1][-1]['mode']=='2x2' and groups[-1][-1]['front'] in c['pairs']:
                groups[-1].append(c)
            else:groups.append([c])
        for group in groups:
            f=group[0];pairids=[next(i for i in f['pairs'] if i!=f['front']),*[c['front'] for c in group]]
            labels=[pairs[i]['members'] for i in pairids];p=b.block(cfg,f['mode'],ch,labels);ts=[]
            for a in p.actions:
                if a.kind=='exposure':v=group[a.owner]['start']
                elif a.kind.startswith('rot_'):v=events[f"{a.kind}_{ch}_{group[a.owner]['index']}"]
                elif a.kind in ('pair_load','pair_unload'):v=events[f"{a.kind[5:]}_{pairids[a.owner]}"]
                else:
                    g,r=divmod(a.owner,2);j=next(j for j in jobs[pairids[g]] if j['identity']==labels[g][r]);v=je[j['name'],a.kind]
                ts.append(round(v*16)/16)
            pieces.append((p,ts))
    return sorted(pieces,key=lambda pt:pt[1][pt[0].cycles[0][0]])

def neighborhood(kind,delta):
    cfg=b.configuration()
    path=(R/'pareto_scales_20261125/two_blocks' if kind=='two' else R/'table4_extended16_20261125/H10/retime')/'schedule.json'
    old=dissect(cfg,path)
    # Dedicated auxiliary loans avoid a legacy label conflict across unrelated chambers;
    # one-chamber duplex loans within each physical sub-batch retain their original coloring.
    result=[];shift=[];sources=[]
    for j,(p,ts) in enumerate(old):
        st=ts[p.cycles[0][0]]
        if kind=='two':
            d=-delta if st>600 else 0;ch=p.chamber
        else:
            # Keep the first two 4x1 cycles and chain; insert the last two 4x1
            # pairs into the open chamber instead of queueing at the end.
            d=0 if j<=1 else -delta if p.mode=='2x2' else (460-st if j==3 else 755-st)
            ch=2 if j>=3 else p.chamber
        new=b.block(cfg,p.mode,ch,p.members)
        result.append(new);sources.append(ts);shift.append(d)
    return cfg,result,sources,shift

def apply(cfg,pats,source,offset,radius,m,vs,pieces,end):
    scale=16
    for (p,base),ts,sh in zip(pieces,source,offset):
        for i,a in enumerate(p.actions):
            k=base+i;aim=ts[i]+sh
            dom=radius if a.kind in ('exposure','pair_load','pair_unload') else min(90,radius+25)
            m.add_linear_constraint(vs[k],max(0,round((aim-dom)*scale)),round((aim+dom)*scale))
        for i,labels in enumerate(p.members):
            if any(x.startswith('LP') for x in labels):
                ld,ul=(p.handling[i,k] for k in ('pair_load','pair_unload'))
                m.add(vs[base+ul]-vs[base+ld]==round((ts[ul]-ts[ld])*scale))
        for g,labels in enumerate(p.members):
            ra,rb=p.routes[g*2],p.routes[g*2+1]
            for motion in set(ra)&set(rb):
                if abs(ts[ra[motion]]-ts[rb[motion]])<.001:
                    m.add(vs[base+ra[motion]]==vs[base+rb[motion]])

def execute(task):
    name,kind,delta,radius=task;folder=OUT/name;folder.mkdir(parents=True,exist_ok=True)
    cfg,pats,sources,shifts=neighborhood(kind,delta)
    ident=dict(task=list(task),source=b.sha(Path(__file__)), engine=b.sha(Path(b.__file__)), objective=score.OBJECTIVE)
    p=folder/'progress.json';done=folder/'done.json';inc=folder/'candidate.json'
    rec=b.read(p) if p.exists() else dict(identity=ident,elapsed=0,best=None)
    assert rec['identity']==ident
    if done.exists():return
    t=time.monotonic();earlier=rec['elapsed'];stop=threading.Event()
    def update():
        rec.update(elapsed=earlier+time.monotonic()-t);put(p,rec)
    def beat():
        while not stop.wait(2):update()
    th=threading.Thread(target=beat,daemon=True);th.start()
    def track(ts,c):
        if rec['best'] is None or c<rec['best']-.0001:
            put(inc,dict(times=ts,cmax=c));rec['best']=c;update()
            print(name,'C=',c,flush=True)
    hints=b.read(inc)['times'] if inc.exists() else [max(0,t+sh) for v,sh in zip(sources,shifts) for t in v]
    try:
        b.time_blocks(cfg,pats,scale=16,ideal=False,seed=2+delta,budget=max(.05,WALL-earlier),workers=2,
                      incumbent=rec['best'] or (1156.24 if kind=='two' else 1360),progress=track,
                      hint_times=hints,specialize=partial(apply,cfg,pats,sources,shifts,radius))
        rec['state']='feasible'
    except RuntimeError as e:rec['state']=str(e).split(' for ')[0]
    finally:stop.set();th.join();update()
    if inc.exists():
        doc=decode(cfg,pats,b.read(inc)['times']);put(folder/'schedule.json',doc);rec['metrics']=score.metrics(doc)
    put(done,rec)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lock=(OUT/'neighborhood.lock').open('a+b')
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        fs=[pool.submit(execute,t) for t in TRIALS]
        while any(not f.done() for f in fs):
            comp=sum((OUT/t[0]/'done.json').exists() for t in TRIALS)
            failed=sum(f.done() and f.exception() is not None for f in fs)
            remaining=sum(0 if(OUT/t[0]/'done.json').exists() else max(0,WALL-(b.read(OUT/t[0]/'progress.json')['elapsed'] if(OUT/t[0]/'progress.json').exists() else 0)) for t in TRIALS)/2
            put(OUT/'neighborhood_progress.json',dict(completed=comp,total=len(TRIALS),failed=failed,elapsed=time.monotonic()-start,remaining=remaining,estimated_total=time.monotonic()-start+remaining,basis='2 concurrent CP jobs, cumulative 38s per neighborhood'))
            print(comp,'/',len(TRIALS),'failed',failed,'elapsed',round(time.monotonic()-start),'remaining',round(remaining),flush=True);time.sleep(2)
        for f in fs:f.result()
    put(OUT/'neighborhood_progress.json',dict(completed=len(TRIALS),failed=0,elapsed=time.monotonic()-start,remaining=0))
if __name__=='__main__':main()
