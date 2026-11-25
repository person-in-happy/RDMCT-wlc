"""Resume the original one-percent, common-warm-pool comparison for the two new cases."""
import argparse
import json
import msvcrt
import os
import subprocess
import sys
import time
from pathlib import Path

from blocks import HERE,JMS,OUT,metrics,read,sha,validate,write

R=JMS/'results'
oldmix=R/'table3_mixed16_20261125'
solver=HERE.parent/'huber_residence_20261125/solver.py'


def relative(path):
    return path.relative_to(JMS).as_posix()


def input_pair(h):
    if h==10:
        a=oldmix/'witnesses/proposals__moves810__candidate_810'
        proof=R/'table3_grid16_20261125/ranked/mixed_809/summary.json'
        cert=read(proof)
        assert cert['failed']==0 and cert['completed']==cert['count']==cert['infeasible'] and cert['lower']==810
        return a,proof,810
    entry=read(OUT/'H3/handoff.json')
    a=JMS/entry['source'];proof=JMS/entry['lower_source']
    assert sha(proof)==entry['lower_sha256']
    assert sha(a/'schedule.json')==entry['schedule_sha256']
    return a,proof,entry['lower']


def run(h):
    group=OUT/f'H{h}';group.mkdir(parents=True,exist_ok=True)
    lock=(group/'compare.lock').open('ab+')
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print('The active foreground worker owns this case.',flush=True);return
    start=time.monotonic()
    a,p,lower=input_pair(h);c=read(a/'primary.json');doc=read(a/'schedule.json')
    f=metrics(doc)
    assert c['schedule_sha256']==sha(a/'schedule.json') and c['assignment_sha256']==sha(a/'assignment.json.gz')
    assert c['rows'] and c['replay']['valid'] and validate(doc)['valid']
    assert lower<=f['cmax']+1e-6 and f['cmax']<=1.01*lower+1e-6
    assert doc['config']['cleaning_interval']==h
    seedwall=[]
    for seed in (1,2,3):
        branch=group/f's{seed}';branch.mkdir(exist_ok=True)
        primary=branch/'A.json'
        spec=dict(seed=seed,scope='all input-feasible structures',target_gap=.01,source=relative(a),
                  model_rows=c['rows'],schedule_sha256=c['schedule_sha256'],assignment_sha256=c['assignment_sha256'],
                  lower_source=relative(p),lower_sha256=sha(p),lower=lower,upper=f['cmax'],
                  gap=(f['cmax']-lower)/lower,metrics=f,initial_gap_satisfied=True,
                  warm_policy='The same archive pool and global bound are visible to each seed; A selects the shortest validated product-return schedule before checking its stopping gap.')
        if primary.exists():assert read(primary)==spec
        else:write(primary,spec)
        archive=oldmix/'grid/0p01pct/1pct' if h==10 and seed==1 else branch/'AB'
        if (archive/'result.json').exists():
            b=read(archive/'result.json')
        else:
            archive.mkdir(exist_ok=True)
            log=branch/'solver_console.log'
            cmd=[sys.executable,'-B','-u','-X','utf8',str(solver),'--mode','fixed','--source',str(a),
                 '--output',str(archive),'--seed',str(seed),'--gap','.01']
            with log.open('ab') as stream:
                proc=subprocess.Popen(cmd,stdout=stream,stderr=subprocess.STDOUT)
                while proc.poll() is None:
                    elapsed=time.monotonic()-start
                    done=seed-1
                    # Prior native 16-wafer fixed-skeleton replays took about a minute per endpoint.
                    basis=sum(seedwall)/len(seedwall) if seedwall else 65
                    eta=max(0,(4-seed)*basis)
                    write(group/'compare_progress.json',dict(completed=done,expected=3,failed=0,active_seed=seed,
                          elapsed_s=elapsed,remaining_estimate_s=eta,total_estimate_s=elapsed+eta,
                          basis='16-wafer native endpoint wall time; single worker per case',pid=proc.pid))
                    print(f'H={h} A/AB seed {seed}; {done}/3 complete, 0 failed, elapsed {elapsed:.1f}s, ETA ~{eta:.0f}s',flush=True)
                    time.sleep(4)
                if proc.returncode:raise RuntimeError(f'Native worker exited {proc.returncode}; {log}')
            b=read(archive/'result.json')
            seedwall.append(b['record']['wall_seconds'])
        assert b['eligible'] and b['seed']==seed and b['target_gap']==.01 and b['replay']['valid']
        assert b['mode']=='fixed' and b['parents'][0]['schedule_sha256']==c['schedule_sha256'] and b['parents'][0]['assignment_sha256']==c['assignment_sha256']
        assert b['record']['gap']<=.0100002
        assert b['original_rows']==b['replayed_rows']==c['rows'] and b['files']['schedule.json']==sha(archive/'schedule.json')
        bdoc=read(archive/'schedule.json');assert validate(bdoc)['valid']
        fb=metrics(bdoc)
        assert abs(fb['cmax']-f['cmax'])<.0002 and all(abs(v-b['measured'][k])<.0002 for k,v in fb.items())
        write(branch/'AB.json',dict(seed=seed,certificate=relative(archive/'result.json'),certificate_sha256=sha(archive/'result.json'),
                source=relative(archive),metrics=fb,lower=b['record']['lower'],upper=b['record']['upper']))
    elapsed=time.monotonic()-start
    write(group/'compare_progress.json',dict(completed=3,expected=3,failed=0,elapsed_s=elapsed,remaining_estimate_s=0))
    print(f'H={h} 3/3 complete, 0 failed, remaining 0s',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('h',type=int);run(p.parse_args().h)
