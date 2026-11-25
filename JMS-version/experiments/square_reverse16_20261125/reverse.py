"""Reverse endpoint search with independently exchangeable robot orders and fixed chamber batches."""
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
import msvcrt
import sys, os, time, inspect, threading
HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1];OUT=JMS/'results'/HERE.name
sys.path.insert(0,str(HERE.parent/'table4_extended16_20261125'))
import blocks as b
sp=importlib.util.spec_from_file_location('square_score_standalone',HERE.parent/'square_residence_20261125/score.py')
score=importlib.util.module_from_spec(sp);sp.loader.exec_module(score)
LOCK=threading.RLock()
BUDGET=45
TASKS=[
 ('a', [126,337,562,784], 275, 52),
 ('b', [125,329,545,779], 365, 58),
 ('c', [119,345,585,847], 227, 62),
 ('d', [125,360,620,866], 410, 80),
]

def load_blocks():
    cfg=b.configuration()
    one,two=[j['wafers'] for j in cfg.pjobs]
    pats=[b.block(cfg,'4x1',3,[['D1','D2'],one[i:i+2]]) for i in range(0,8,2)]
    pats.append(b.block(cfg,'2x2',2,[['D3','D4'],two[0:2],two[2:4],two[4:6],[two[6],'D5'],[two[7],'D6'],['D7','D8']]))
    return cfg,pats

def specialize(ch_starts,radius,m,vs,parts,end):
    scale=16
    for k,(p,off) in enumerate(parts):
        x=vs[off+p.cycles[0][0]]
        m.add_linear_constraint(x,scale*(ch_starts[k]-radius),scale*(ch_starts[k]+radius))
        if k==4:
            for q,(expo,_,_) in enumerate(p.cycles):
                d=min(q,4)*94.5625+(94 if q==5 else 0)
                m.add(vs[off+expo]==x+int(d*scale))
        for g,labels in enumerate(p.members):
            if all(w.startswith('LP') for w in labels):
                ra,rb=p.routes[g*2],p.routes[g*2+1]
                m.add(vs[off+ra['al_put']]<=vs[off+rb['al_put']])
                for name in ('origin_pick','destination_put','lower_pick','origin_put'):
                    m.add(vs[off+ra[name]]==vs[off+rb[name]])
            elif len(set(w[0] for w in labels))==1:
                for label in ('source_pick','destination_put'):
                    m.add(vs[off+p.routes[g*2][label]]==vs[off+p.routes[g*2+1][label]])

def decode(cfg,pats,ts):
    offs=[];offset=0
    for p in pats:
        offs.append((p,offset));offset+=len(p.actions)
    def normalize(c,doc):
        data=b.normalize_schedule(c,doc)
        if not b.attach_hands(data):raise ValueError('gripper coloring rejected')
        return data
    with patch('timing.normalize_schedule',normalize):
        return b.BatchTiming.schedule(SimpleNamespace(cfg=cfg,blocks=offs),ts)

def put(path,data):
    with LOCK:b.write(path,data)

def run_one(task):
    name,short,long,radius=task;folder=OUT/name;folder.mkdir(parents=True,exist_ok=True)
    cfg,pats=load_blocks()
    ident=dict(task=task, source=b.sha(Path(__file__)), model=b.sha(Path(b.__file__)), objective=score.OBJECTIVE)
    status=folder/'progress.json';done=folder/'done.json';best=folder/'candidate.json'
    import json
    ident=json.loads(json.dumps(ident))
    old=b.read(status) if status.exists() else dict(identity=ident,elapsed=0,best=None)
    assert old['identity']==ident
    if done.exists():return
    started=time.monotonic();earlier=old['elapsed'];stop=threading.Event()
    def write():
        old.update(elapsed=earlier+time.monotonic()-started)
        put(status,old)
    def monitor():
        while not stop.wait(3):write()
    th=threading.Thread(target=monitor,daemon=True);th.start()
    def track(ts,c):
        if old['best'] is None or c<old['best']-1e-7:
            old['best']=c;put(best,dict(times=ts,cmax=c));write()
            print(name,'endpoint',c,flush=True)
    try:
        b.time_blocks(cfg,pats,scale=16,ideal=True,seed=1+ord(name[0]),budget=max(.05,BUDGET-earlier),
            incumbent=min(1260,old['best']) if old['best'] else 1260,
            specialize=partial(specialize,short+[long],radius),workers=2,
            hint_times=b.read(best)['times'] if best.exists() else None,progress=track)
        old['status']='feasible'
    except RuntimeError as e:old['status']=str(e).split(' for ')[0]
    finally:stop.set();th.join();write()
    if best.exists():
        doc=decode(cfg,pats,b.read(best)['times']);put(folder/'schedule.json',doc)
        old['metrics']=score.metrics(doc)
    put(done,old)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lock=(OUT/'run.lock').open('a+b')
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print('Existing session owns this run; showing progress',flush=True);return
    t=time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run_one,task) for task in TASKS]
        while not all(f.done() for f in futures):
            completed=sum((OUT/v[0]/'done.json').exists() for v in TASKS)
            failed=sum(f.done() and f.exception() is not None for f in futures)
            used=[min(BUDGET,b.read(OUT/v[0]/'progress.json')['elapsed']) if (OUT/v[0]/'progress.json').exists() else 0 for v in TASKS]
            left=sum(BUDGET-x for x in used)/2
            state=dict(completed=completed,failed=failed,total=len(TASKS),elapsed=time.monotonic()-t,
                       estimated_total=time.monotonic()-t+left,remaining=left,basis='two parallel cumulative 45s CP solves, construction and verification overhead excluded')
            put(OUT/'progress.json',state)
            print('Reverse16:',completed,'/',len(TASKS),'failed',failed,'elapsed',round(state['elapsed']),'ETA',round(left),'s',flush=True)
            time.sleep(3)
        for f in futures:f.result()
    put(OUT/'progress.json',dict(completed=len(TASKS),failed=0,total=len(TASKS),elapsed=time.monotonic()-t,remaining=0))
if __name__=='__main__':main()
