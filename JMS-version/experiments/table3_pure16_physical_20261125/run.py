"""Resume compact 16-product cases in two visible foreground worker slots."""
from pathlib import Path
import sys,time,subprocess,os,json,msvcrt
from concurrent.futures import ThreadPoolExecutor
from physical import HERE,DEST,BASE,JMS,save,load,sha

OUT=JMS/'results/table3_pure16_active_20261125'

def search(spec):
    score,cap,window,seconds=spec;src=BASE/f'4x1/projection/candidate_{score}.json'
    path=OUT/f'projected{score}_cap{cap}_window{window}'
    command=[sys.executable,'-B','-u','-X','utf8',str(HERE/'physical.py'),str(src),str(cap),str(window),str(seconds),str(path)]
    path.mkdir(exist_ok=True,parents=True)
    with (path/'output.log').open('a',encoding='utf8') as log:
        subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    return path

def main():
    OUT.mkdir(exist_ok=True);f=(OUT/'run.lock').open('a+b');f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
    specs=[(862,915,2,70),(855,910,2,70),(870,910,6,70),(855,885,10,100)]
    with ThreadPoolExecutor(2) as pool:
        jobs={s:pool.submit(search,s) for s in specs};started=time.monotonic()
        while True:
            done=[s for s,x in jobs.items() if x.done() and x.exception() is None];failed=[s for s,x in jobs.items() if x.done() and x.exception()];
            remain=[];best=[]
            for score,cap,w,b in specs:
                d=OUT/f'projected{score}_cap{cap}_window{w}';state=load(d/'progress.json') if (d/'progress.json').exists() else {}
                if state.get('upper') is not None:best.append(state['upper'])
                if not (d/'result.json').exists() and (score,cap,w,b) not in failed:remain.append(max(0,b-state.get('used',0)))
            elapsed=time.monotonic()-started;eta=max(max(remain,default=0),sum(remain)/2)
            status=dict(completed=done,failed=failed,upper=min(best,default=None),elapsed_s=elapsed,remaining_s=eta,estimated_total_s=elapsed+eta,estimate='Remaining charged solver limits on two single-core workers; build/validation overhead excluded.')
            save(OUT/'progress.json',status);print(f'Complete {len(done)}/{len(jobs)}, failed {len(failed)}; elapsed {elapsed:.0f}s, total ~{elapsed+eta:.0f}s, remaining ~{eta:.0f}s; best={status["upper"]}',flush=True)
            if len(done)+len(failed)==len(jobs):break
            time.sleep(3)
        if failed:raise RuntimeError(failed)

if __name__=='__main__':main()
