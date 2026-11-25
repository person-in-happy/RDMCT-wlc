"""Refine the shared 16-wafer physical endpoint and sample the adjacent dwell spread."""
from refine import *
GROUPS=[('tight',[(7,12,23),(7,8,11)]),('broad',[(7,18,35),(7,4,15)])]
def branch(entry):
    name,opts=entry;path=OUT/'steps_narrow2/schedule.json'
    for i,(d,s,r) in enumerate(opts):
        folder=OUT/f'last_{name}{i}';step(f'last_{name}{i}',folder,path,d,s,r)
        if (folder/'schedule.json').exists() and b.read(folder/'schedule.json')['cmax']<=b.read(path)['cmax']+.00001:
            path=folder/'schedule.json'
    for d in ([8,10,13,16] if name=='tight' else [9,11,12,15]):
        f=OUT/(f'last_{name}_d{d}');step(f'last_{name}_d{d}',f,path,d,0,8)
def main():
    lk=(OUT/'last.lock').open('a+b')
    try:msvcrt.locking(lk.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as ex:
        fs=[ex.submit(branch,x) for x in GROUPS]
        while any(not f.done() for f in fs):
            n=len(list(OUT.glob('last_*/done.json')));bad=sum(f.done() and f.exception() is not None for f in fs)
            left=max(0,(12-n)*LIM/2-sum(b.read(p)['elapsed'] for p in OUT.glob('last_*/progress.json') if not(p.parent/'done.json').exists())/2)
            dt=time.monotonic()-start
            put(OUT/'last_progress.json',dict(completed=n,failed=bad,elapsed=dt,total=12,estimated_total=dt+left,remaining=left,basis='two workers, twelve cumulative 24s upper budgets plus verification'))
            print(n,'/12',bad,'failed, elapsed',round(dt),'remaining <=',round(left),flush=True);time.sleep(3)
        for f in fs:f.result()
    put(OUT/'last_progress.json',dict(completed=12,failed=0,total=12,elapsed=time.monotonic()-start,remaining=0))
if __name__=='__main__':main()
