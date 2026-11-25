"""Foreground full-load and partial-load alternatives with independent per-plan checkpoints."""
import msvcrt,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor
from physical import HERE,JMS,BASE,SOURCE,CFG,STEPS,load,save,sha,cell,sparse_witness,normalize_schedule,compressed,validate
from full_plans import prepare

OUT=JMS/'results/table3_pure16_active_20261125'
SHARED=BASE/'4x1/search/active_order_validation'

def certify(data,source):
    c=int(data['cmax']);p=SHARED/f'schedule_{c}.json';meta=SHARED/f'event_{c}.json'
    if meta.exists():return
    sol=cell.lift(CFG,sparse_witness(CFG,data),None,rebuild=True)
    if not sol or not sol[3]['valid']:raise ValueError('Native witness rejected')
    doc,vs,_,replay,rows=sol;assert replay['product_return_cmax']==c
    save(p,doc);material=OUT/'certified'/str(c);material.mkdir(exist_ok=True,parents=True)
    compressed(material/'assignment.json.gz',vs)
    save(meta,dict(cmax=c,timestamp=time.time(),rows=rows,replay=replay,schedule_sha256=sha(p),source=str(source.relative_to(JMS)),source_sha256=sha(source),
                   assignment_sha256=sha(material/'assignment.json.gz'),scope='original feasible upper bound only'))

def task(spec):
    source,cap,w,b,tag=spec
    p=OUT/tag;p.mkdir(exist_ok=True,parents=True)
    with (p/'output.log').open('a',encoding='utf8') as log:
        subprocess.run([sys.executable,'-B','-u','-X','utf8',str(HERE/'physical.py'),str(source),str(cap),str(w),str(b),str(p)],check=True,stdout=log,stderr=subprocess.STDOUT)

def main():
    OUT.mkdir(exist_ok=True,parents=True);SHARED.mkdir(exist_ok=True,parents=True)
    f=(OUT/'refine.lock').open('a+b');f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
    ref=prepare()/'reference920.json';d=BASE/'4x1/projection'
    source=JMS/'results/sublevel_projection_20261120_r1/D_n16_4x1/complete/schedule.json'
    specs=[(ref,920,12,40,'full12'),(d/'candidate_855.json',920,10000,40,'mixed855_free'),(ref,920,10000,80,'full_free'),(d/'candidate_862.json',920,10000,70,'mixed862_free')]
    t=time.monotonic()
    with ThreadPoolExecutor(1) as pool:
        jobs={s:pool.submit(task,s) for s in specs};best=100000
        while True:
            candidates=[(920,source)]+[(int(p.stem.split('_')[1]),p) for *_,tag in specs for p in (OUT/tag).glob('schedule_*.json')]
            number,path=min(candidates,key=lambda x:x[0]);done=[s[-1] for s,x in jobs.items() if x.done() and not x.exception()];failed=[s[-1] for s,x in jobs.items() if x.done() and x.exception()]
            remaining=[]
            for _,_,_,b,tag in specs:
                if tag in done+failed:continue
                state=OUT/tag/'progress.json';remaining.append(max(0,b-(load(state)['used'] if state.exists() else 0)))
            eta=sum(remaining); elapsed=time.monotonic()-t
            save(OUT/'refine_status.json',dict(completed=done,failed=failed,best=number,elapsed_s=elapsed,total_s=elapsed+eta,remaining_s=eta,
                   basis='One search worker with cumulative checkpointed per-plan budgets, one concurrent native verifier.'))
            print(f'Complete {len(done)}/4 failed {len(failed)}; best {number}s; elapsed {elapsed:.0f}s, remaining ~{eta:.0f}s',flush=True)
            if number<best:
                doc=load(path);doc=normalize_schedule(CFG,doc) if path==source else doc
                certify(doc,path);best=number
            if len(done)+len(failed)==len(jobs):break
            time.sleep(2)
        if failed:raise RuntimeError(failed)

if __name__=='__main__':main()
