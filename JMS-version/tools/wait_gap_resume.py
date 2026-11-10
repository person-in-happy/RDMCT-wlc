"""Wait in the foreground for a frozen gap campaign's RAM, then resume it.

Does not change campaign settings, driver code, completed cells or failures.
Only an explicitly identified between-cell RAM admission stop is retried.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import psutil

DRIVER = Path(__file__).with_name('default_gap_experiments.py')
ROOT = DRIVER.resolve().parents[2]
RAM_STOP = re.compile(r'^RuntimeError: Need \d+ MiB; available \d+\. Frozen budget retained; resume after freeing RAM\.$')


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


def inspect(out):
    if hashlib.sha256((out / 'campaign.json').read_bytes()).hexdigest() != read(out / 'contract.json')['campaign_sha256']:
        raise RuntimeError('Frozen campaign changed')
    spec = read(out / 'campaign.json')
    st = spec['settings']
    return st['process_memory_mb'] + st['reserve_mb']


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--campaign', required=True)
    p.add_argument('--check', action='store_true', help='Validate and report only; no wait or solver')
    a = p.parse_args()
    out = Path(a.campaign).resolve()
    required = inspect(out)
    # Driver verifies all frozen code, input and completed-result hashes.
    subprocess.run([sys.executable, '-X', 'utf8', str(DRIVER), 'status', '--campaign', str(out)],
                   cwd=ROOT, check=True)
    coverage = read(out / 'summary/coverage.json')
    available = psutil.virtual_memory().available / 1024**2
    print(json.dumps(dict(required_mib=required, available_mib=round(available),
                          launch_margin_mib=512, solver_started=False)), flush=True)
    if a.check or coverage['complete'] == coverage['expected']:
        return
    if coverage['failed']:
        raise RuntimeError('Known failures retained. Diagnose them before retrying; this wrapper does not retry failures.')
    while True:
        while True:
            available = psutil.virtual_memory().available / 1024**2
            if available >= required + 512:
                break
            print(f'WAIT RAM available={available:.0f}MiB frozen_required={required}MiB '
                  f'launch_target={required + 512}MiB; recheck in 15s; Ctrl+C exits safely', flush=True)
            time.sleep(15)
        print('RESUME with unchanged frozen settings', flush=True)
        child = subprocess.Popen([sys.executable, '-X', 'utf8', '-u', str(DRIVER),
            'resume', '--campaign', str(out)], cwd=ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        ram_stop = False
        try:
            for line in child.stdout:
                print(line, end='', flush=True)
                if RAM_STOP.fullmatch(line.strip()):
                    ram_stop = True
            code = child.wait()
        except BaseException:
            # The visible terminal delivers Ctrl+C to the process group. Allow
            # the driver to preserve its interrupted worker before returning.
            try:
                child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                raise RuntimeError('Driver has not exited; inspect its PID before another resume')
            raise
        finally:
            child.stdout.close()
        if code == 0:
            return
        if not ram_stop:
            raise SystemExit(code)
        print('RAM admission stopped between cells; completed observations retained. Waiting again.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Stopped by user; resume the same campaign later.', flush=True)
        raise SystemExit(130)
