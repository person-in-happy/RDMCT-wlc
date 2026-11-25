"""Try adjacent product groupings and allow optional pair synchronization in each fixed group plan."""
import itertools,msvcrt,subprocess,sys,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event,Thread
from physical import HERE,JMS,BASE,SOURCE,CFG,STEPS,load,save,sha,make,cp_model
from full_plans import to_slots
from refine import certify,SHARED

OUT=JMS/'results/table3_pure16_active_20261125/alternatives'
START=SHARED/'schedule_858.json'

def prepare(tag,back_counts):
    src=OUT/tag/'skeleton.json'
    if src.exists():return src
    original=load(START);slots={};ids=iter(range(16))
    layout=[(0,0,4),(1,0,4),(0,1,3),(1,1,3),(0,2,2)]
    for (ch,q,count),back in zip(layout,back_counts):
        slots[f'use{ch,q}']=1
        for i in range(count):slots[f'w{next(ids)}_{ch}_{q}_{int(i>=back)}']=1
    if tag=='old_free':slots=to_slots(original,'4x1')
    if tag.startswith('ordered'):
        raw=load(JMS/'results/table3_grid16_20261125/ordered/4x1_844/projection.json')
        ids=sorted(int(k.split('_')[1]) for k in raw if k.startswith('kind_'))
        order=sorted(range(16),key=lambda i:raw[f'al_{i}']) if tag=='ordered_al' else list(range(16))
        slots={};positions={i:j for j,i in enumerate(order)}
        for i in range(16):
            group=ids[raw[f'batch_{i}']];ch,q=divmod(group,10);side=raw[f'front_{i}'];slots[f'use{ch,q}']=1
            slots[f'w{positions[i]}_{ch}_{q}_{side}']=1
    save(src,slots);return src

def worker(tag,back,limit):
    src=prepare(tag,back);d=src.parent;p=d/'progress.json'
    state=load(p) if p.exists() else dict(used=0,best=None,identity=dict(skeleton=sha(src),original=sha(START),make=sha(HERE/'physical.py'),code=sha(Path(__file__)),cap=858,seconds=limit,seed=1))
    assert state['identity']['code']==sha(Path(__file__)) and state['identity']['skeleton']==sha(src)
    if (d/'result.json').exists():return
    model,decode=make(src,858,10000);model.clear_hints()
    # The parent product-route projection already enforces exactly the native alternatives (same pair, same action, same station).
    # Remove the extra unconditional product synchronizations introduced by using blank times in the neighborhood template.
    import re
    names=[v.name for v in model.proto.variables];released=0
    for row in model.proto.constraints:
        if not row.has_linear() or row.enforcement_literal or len(row.linear.vars)!=2 or list(row.linear.domain)!=[0,0]:continue
        a,b=[re.fullmatch(r'(\d+)_(origin_pick|origin_put|upper_put|lower_pick|source_pick|destination_put)',names[i]) for i in row.linear.vars]
        if a and b and a[1]!=b[1] and a[2]==b[2]:row.clear_linear();released+=1
    first=load(START);ev={(e.get('job'),e['kind']):e['start'] for e in first['events'] if 'job' in e};hints={}
    for i,w in enumerate(sorted([j for j in first['jobs'] if j['product']],key=lambda w:w['pjob_index'])):
        for n in STEPS:hints[f'{i}_{n}']=int(w[n+'_start'] if n in ('load','unload') else ev[w['name'],n])
    for i,name in enumerate(names):
        if name in hints:model.add_hint(model.get_int_var_from_proto_index(i),hints[name])
    if state['best'] is not None:model.add(model.get_int_var_from_proto_index(names.index('makespan'))<state['best'])
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=1
    charged=state['used'];t=time.monotonic();solver.parameters.max_time_in_seconds=max(.05,limit-charged);stop=Event();errors=[]
    def pulse():
        while not stop.wait(1):state['used']=min(limit,charged+time.monotonic()-t);save(p,state)
    class C(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            try:
                physical=decode(self);score=physical['cmax'];save(d/f'schedule_{score}.json',physical);state['best']=score
            except Exception as exc:errors.append(exc);self.stop_search()
    th=Thread(target=pulse);th.start()
    try:status=solver.solve(model,C())
    finally:stop.set();th.join()
    if errors:raise errors[0]
    state['used']=min(limit,charged+time.monotonic()-t);save(p,state)
    save(d/'result.json',dict(state,fixed_bound=solver.best_objective_bound,sync_rows_released=released,status=solver.status_name(status)))

def main():
    OUT.mkdir(exist_ok=True,parents=True);f=(OUT/'control.lock').open('a+b');f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
    specs=[('ordered_al',(),65),('ordered_index',(),65),('old_free',(2,2,1,1,0),50)]+[(f'{a}{b}{c}',(2,2,a,b,c),45) for a,b,c in itertools.product((2,1),(2,1),(0,1,2))]
    t=time.monotonic();best=858
    for i in range(0,len(specs),2):
        wave=specs[i:i+2];processes=[]
        for tag,back,secs in wave:
            path=OUT/tag;path.mkdir(exist_ok=True);f=(path/'worker.log').open('a',encoding='utf8')
            child=subprocess.Popen([sys.executable,'-B','-u','-X','utf8',str(HERE/'alternatives.py'),tag,','.join(map(str,back)),str(secs)],stdout=f,stderr=subprocess.STDOUT);processes.append((child,f))
        while any(c.poll() is None for c,_ in processes):
            done=[a for a,_,_ in specs if (OUT/a/'result.json').exists()];remain=[]
            for a,_,sec in specs:
                if a in done:continue
                p=OUT/a/'progress.json';remain.append(sec-(load(p)['used'] if p.exists() else 0))
            eta=max(max(remain,default=0),sum(remain)/2);elapsed=time.monotonic()-t
            save(OUT/'status.json',dict(done=done,active=[w[0] for w in wave],failed=[],elapsed_s=elapsed,total_s=elapsed+eta,remaining_s=eta,best_certified=best,basis='Cumulative CP limits, two simultaneous one-thread cases.'))
            print(f'Completed {len(done)}/{len(specs)}, 0 failed, elapsed {elapsed:.0f}s, estimated total {elapsed+eta:.0f}s, remaining {eta:.0f}s; upper {best}',flush=True);time.sleep(2)
        for child,log in processes:log.close();assert child.returncode==0
        candidates=[(int(p.stem.split('_')[1]),p) for tag,_,_ in wave for p in (OUT/tag).glob('schedule_*.json')]
        if candidates:
            n,p=min(candidates,key=lambda v:v[0]);
            if n<best:certify(load(p),p);best=n
    save(OUT/'status.json',dict(done=[s[0] for s in specs],failed=[],elapsed_s=time.monotonic()-t,remaining_s=0,best_certified=best))

if __name__=='__main__':
    if len(sys.argv)>1:worker(sys.argv[1],tuple(int(s) for s in sys.argv[2].split(',') if s),int(sys.argv[3]))
    else:main()
