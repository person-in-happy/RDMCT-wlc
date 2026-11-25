"""Move the single long 2x2 chain and four 4x1 pairs while preserving its global score."""
from neighborhood import *
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
import json
REL=[('old_steep',None,[0,0,-45,-80,-80],45),('old_mild',None,[0,0,0,-30,-30],25),
     ('float_mid',[2,3,3,2,2],[0,0,-45,-520,-350],60),
     ('float_free',[2,3,3,2,2],[0,0,0,-570,-365],52),
     ('wide_insert',[2,3,3,2,2],[0,0,-60,-600,-400],96)]
LIMIT=38

def flex_decode(cfg,pats,ts):
    pieces=[];off=0
    for p in pats:pieces.append((p,off));off+=len(p.actions)
    def fix(c,raw):
        refs={p['id']:p for p in raw['pairs']};avail=[-1.]*8
        aux=sorted([j for j in raw['jobs'] if not j['product']],key=lambda w:(w['loan_start'],w['loan_end'],w['name']))
        for j in aux:
            h=next(i for i,t in enumerate(avail) if t<=j['loan_start']+.00001)
            avail[h]=j['loan_end'];r=int(j['name'].split('_')[-1]);j['identity']=refs[j['pair']]['members'][r]=f'D{h+1}'
        d=b.normalize_schedule(c,raw);assert b.attach_hands(d);return d
    with patch('timing.normalize_schedule',fix):
        return b.BatchTiming.schedule(SimpleNamespace(cfg=cfg,blocks=pieces),ts)

def decorate(source,shifts,radius,m,vs,pieces,end):
    cfg=b.configuration();pats=[p for p,off in pieces]
    apply(cfg,pats,source,shifts,radius,m,vs,pieces,end)
    holds=[]
    for p,off in pieces:
        for g,members in enumerate(p.members):
            for j,w in enumerate(members):
                if w.startswith('D'):
                    r=p.routes[2*g+j];size=m.new_int_var(0,80000,'')
                    holds.append(m.new_interval_var(vs[off+r['source_pick']],size,vs[off+r['destination_put']]+16,''))
    m.add_cumulative(holds,[1]*len(holds),8)

def execute_flex(task):
    name,chs,shifts,radius=task;folder=OUT/name;folder.mkdir(parents=True,exist_ok=True)
    cfg=b.configuration();src=R/'table4_extended16_20261125/H10/retime/schedule.json'
    family=dissect(cfg,src)
    if not chs:chs=[p.chamber for p,ts in family]
    ident=dict(task=task,source=b.sha(Path(__file__)),parent=b.sha(src));ident=json.loads(json.dumps(ident))
    status=folder/'progress.json';done=folder/'done.json';cand=folder/'candidate.json'
    rec=b.read(status) if status.exists() else dict(identity=ident,elapsed=0,best=None)
    assert rec['identity']==ident
    if done.exists():return
    pats=[];sources=[];aux=100
    for k,(p,ts) in enumerate(family):
        labels=[]
        for g in p.members:
            new=[]
            for w in g:
                if w.startswith('D'):aux+=1;w=f'D{aux}'
                new.append(w)
            labels.append(new)
        pats.append(b.block(cfg,p.mode,chs[k],labels));sources.append(ts)
    start=time.monotonic();base=rec['elapsed'];stop=threading.Event()
    def update():rec['elapsed']=time.monotonic()-start+base;put(status,rec)
    def beat():
        while not stop.wait(2):update()
    th=threading.Thread(target=beat,daemon=True);th.start()
    def track(ts,c):
        if rec['best'] is None or c<rec['best']-.00001:
            put(cand,dict(times=ts,fA=c));rec['best']=c;update()
            print(name,'C',c,flush=True)
    hints=b.read(cand)['times'] if cand.exists() else [max(0,t+sh) for ts,sh in zip(sources,shifts) for t in ts]
    try:
        b.time_blocks(cfg,pats,scale=16,ideal=False,seed=31+radius,budget=max(.05,LIMIT-base),workers=2,
                      incumbent=rec['best'] or 1446.125,progress=track,hint_times=hints,
                      specialize=partial(decorate,sources,shifts,radius))
        rec['state']='feasible'
    except RuntimeError as e:rec['state']=str(e).split(' for ')[0]
    finally:stop.set();th.join();update()
    if cand.exists():
        with LOCK:doc=flex_decode(cfg,pats,b.read(cand)['times'])
        put(folder/'schedule.json',doc);rec['metrics']=score.metrics(doc)
    put(done,rec)
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lk=(OUT/'move.lock').open('a+b')
    try:msvcrt.locking(lk.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    st=time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as ex:
        fs=[ex.submit(execute_flex,t) for t in REL]
        while any(not f.done() for f in fs):
            counts=[sum((OUT/t[0]/'done.json').exists() for t in REL),sum(f.done() and f.exception() is not None for f in fs)]
            left=sum(0 if(OUT/t[0]/'done.json').exists() else max(0,LIMIT-(b.read(OUT/t[0]/'progress.json')['elapsed'] if(OUT/t[0]/'progress.json').exists() else 0)) for t in REL)/2
            dt=time.monotonic()-st
            put(OUT/'move_progress.json',dict(completed=counts[0],failed=counts[1],total=len(REL),elapsed=dt,estimated_total=dt+left,remaining=left,basis='2 concurrent 38s runs, excluding native replay'))
            print(counts[0],'/',len(REL),'failed',counts[1],'elapsed',round(dt),'remaining',round(left),flush=True);time.sleep(3)
        for f in fs:f.result()
    put(OUT/'move_progress.json',dict(completed=len(REL),failed=0,total=len(REL),elapsed=time.monotonic()-st,remaining=0))
if __name__=='__main__':main()
