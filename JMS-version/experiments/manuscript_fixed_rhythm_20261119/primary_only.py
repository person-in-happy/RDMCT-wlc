"""Resume the full-domain A stages without invoking an archived B implementation."""
import msvcrt
import time

from secondary import OUT, PRIMARY
from design import EXTENSIONS, LEVELS, ROOT, TUNING, read, sha
from campaign import evidence, fingerprint, ready, start
import psutil


def run():
    with (PRIMARY/'controller.lock').open('a+b') as lock:
        lock.seek(0)
        try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print('The active primary controller already owns this campaign.',flush=True)
            return
        protocol=read(PRIMARY/'protocol.json')
        if sha(PRIMARY/'protocol.json')!=read(PRIMARY/'contract.json')['sha256'] or fingerprint()!=protocol['assets']:
            raise ValueError('Changed full-domain solver or protocol')
        for name,expected in protocol['inputs'].items():
            if sha(ROOT/name)!=expected: raise ValueError('Changed input '+name)
        while True:
            tasks=[]
            for c in TUNING:
                tasks.append((c,'prep','full','-','-'))
                tasks.extend((c,'A','full',a,'-') for a in LEVELS)
            summary=OUT/'report.json'
            chosen=read(summary)['selected'] if summary.exists() else None
            if chosen:
                for c in TUNING:
                    tasks.extend((c,'A',arm,chosen['A'],'-') for arm in ('no_spbs','no_rerank'))
                for c in EXTENSIONS:
                    tasks.extend([(c,'prep','full','-','-'),(c,'A','full',chosen['A'],'-')])
            remaining=[t for t in tasks if not evidence(PRIMARY,t)]
            if not remaining and chosen: return
            for task in remaining:
                c,s,arm,a,b=task
                n=protocol['cases'][c]['n']
                if not ready(PRIMARY,task) or psutil.virtual_memory().available/2**30<{2:3.5,4:5,8:7,16:10}[n]: continue
                print(f'A/prep {len(tasks)-len(remaining)}/{len(tasks)}; starting {task}',flush=True)
                process=start(PRIMARY,task)
                try: status=process.wait()
                finally:
                    if process.poll() is None: process.terminate(); process.wait()
                if status: raise RuntimeError(f'Unclosed stage {task}; check its latest attempt')
                break
            else:
                print('Awaiting the complete threshold grid or free memory. ETA unknown.',flush=True)
                time.sleep(20)


if __name__=='__main__': run()
