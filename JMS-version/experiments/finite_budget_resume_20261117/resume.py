"""Resume the existing finite-budget campaign without changing its frozen protocol.

Completed cells are retained. Interrupted cells restart from their predefined
input with a fresh single-cell budget; SCIP search trees are not checkpointed.
All interrupted attempts and stale locks are archived, never erased.
"""
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CAMPAIGN = ROOT / 'JMS-version/results/finite_budget_20261116_r1'
ENTRY = ROOT / 'JMS-version/experiments/finite_budget_20261116/finite_budget.py'
INTERRUPTED = {'foreground_supervisor_interrupted', 'foreground_interrupted'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024**2),b''):
            h.update(block)
    return h.hexdigest()


def safe_path(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Unsafe relative path')
    candidate = root / rel
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path leaves campaign: ' + str(candidate))
    return candidate


def active_processes(out):
    found = []
    for proc in psutil.process_iter(['pid','name','cmdline']):
        try:
            args = proc.info['cmdline'] or []
            if proc.pid == os.getpid() or 'python' not in (proc.info['name'] or '').lower():
                continue
            if not any(Path(arg).name.lower() == 'finite_budget.py' for arg in args):
                continue
            if '--campaign' not in args:
                continue
            path = Path(args[args.index('--campaign')+1])
            if not path.is_absolute():
                path = Path(proc.cwd()) / path
            if path.resolve() == out.resolve():
                found.append(dict(pid=proc.pid, command=args))
        except (psutil.Error, IndexError):
            continue
    return found


def analyze(out, spec):
    complete, interrupted, retained, ambiguous = [], [], [], []
    for cell in spec['cells']:
        cid = cell['id']
        if Path(cid).name != cid or cid in ('.','..'):
            raise ValueError('Unsafe cell identifier')
        dest = safe_path(out, 'runs/' + cid)
        evidence, failure = dest/'evidence.json', dest/'failure.json'
        if evidence.exists():
            if failure.exists():
                ambiguous.append(dict(id=cid,reason='Both evidence and failure exist; review before rerunning'))
            else:
                complete.append(cid)
        elif failure.exists():
            reason = read(failure).get('reason')
            (interrupted if reason in INTERRUPTED else retained).append(dict(id=cid,reason=reason))
        elif dest.exists():
            interrupted.append(dict(id=cid,reason='Incomplete directory; only retry once all old workers are gone'))
    # A cancelled shared preparation can have produced empty dependent failures.
    retry_ids = {r['id'] for r in interrupted}
    cells = {c['id']:c for c in spec['cells']}
    for item in list(retained):
        if item['reason'] == 'shared_preparation_failed' and cells[item['id']].get('preparation') in retry_ids:
            interrupted.append(item)
            retained.remove(item)
    return dict(completed=len(complete), expected=len(spec['cells']), completed_ids=complete,
                interrupted=interrupted, retained_failures=retained, ambiguous=ambiguous)


def check_frozen(out):
    spec = importlib.util.spec_from_file_location('finite_budget_resume_target', ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.checked(out)


def inspect(out):
    spec = read(out/'campaign.json')
    state = analyze(out,spec)
    state['active_processes'] = active_processes(out)
    running = []
    for proc in state['active_processes']:
        args = proc['command']
        if '--cell' in args:
            running.append(args[args.index('--cell')+1])
    state['running_cells'] = running
    state['interrupted'] = [item for item in state['interrupted'] if item['id'] not in running]
    lock = out/'supervisor.lock'
    state['lock_pid'] = int(lock.read_text().strip()) if lock.exists() else None
    state['lock_pid_alive'] = bool(state['lock_pid'] and psutil.pid_exists(state['lock_pid']))
    state['available_gib'] = psutil.virtual_memory().available/1024**3
    state['n16_launch_threshold_gib'] = spec['settings']['launch_reserve_gib']+8.
    state['state'] = 'already_running' if state['active_processes'] else 'stopped'
    return state


def compact(state):
    return {k:v for k,v in state.items() if k != 'completed_ids'}


@contextmanager
def resume_guard(out):
    import msvcrt
    path = safe_path(out,'resume_guard.lock')
    with path.open('a+b') as stream:
        if path.stat().st_size == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)


def archive_interrupted(out, state):
    if state['active_processes'] or active_processes(out):
        raise RuntimeError('Existing supervisor/worker still active; nothing moved')
    if state['lock_pid_alive']:
        raise RuntimeError('Lock PID is alive or reused; inspect instead of removing it')
    if state['ambiguous']:
        raise RuntimeError('Ambiguous completed/failed records need review: ' + json.dumps(state['ambiguous']))
    token = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    archive = safe_path(out,'interrupted_attempts/'+token)
    moves = []
    for item in state['interrupted']:
        cid = item['id']
        for rel in ('runs/'+cid, 'logs/'+cid+'.log', 'launch_records/'+cid+'.json'):
            src = safe_path(out,rel)
            if src.exists():
                dst = safe_path(archive,rel)
                if dst.exists():
                    raise FileExistsError(dst)
                moves.append((src,dst))
    for name in ('supervisor.lock','live_status.json','finished.json'):
        src = safe_path(out,name)
        if src.exists():
            moves.append((src,safe_path(archive,name)))
    # Resolve/check every source and destination before any directory move.
    for src,dst in moves:
        assert src.resolve().is_relative_to(out.resolve())
        assert dst.resolve().is_relative_to(archive.resolve())
        assert archive.resolve().is_relative_to(out.resolve())
    manifest = []
    for src,dst in moves:
        files = list(src.rglob('*')) if src.is_dir() else [src]
        record = dict(source=str(src.relative_to(out)), archived=str(dst.relative_to(out)), files=[])
        for path in files:
            if path.is_file():
                if path.is_symlink() or not path.resolve().is_relative_to(out.resolve()):
                    raise ValueError('Unsafe file in interrupted attempt')
                record['files'].append(dict(relative=str(path.relative_to(src)) if src.is_dir() else path.name,
                                            sha256=sha(path),bytes=path.stat().st_size))
        manifest.append(record)
    if active_processes(out):
        raise RuntimeError('A worker started during preflight; nothing moved')
    archive.mkdir(parents=True,exist_ok=False)
    for src,dst in moves:
        dst.parent.mkdir(parents=True,exist_ok=True)
        src.rename(dst)
    receipt = dict(archived_at=datetime.now(timezone.utc).isoformat(),
                   completed_preserved=state['completed'], restarted_cells=state['interrupted'],
                   retained_failures=state['retained_failures'], moves=manifest,
                   budget_note='Interrupted attempts retained. Retry restarts one cell from the frozen input and original budget; do not hide total attempted computation.')
    (archive/'resume_manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return archive


def run(out):
    state = inspect(out)
    if state['active_processes']:
        print('原批次仍在运行，未重复启动。当前状态：',flush=True)
        print(json.dumps(compact(state),ensure_ascii=False,indent=2),flush=True)
        return
    with resume_guard(out):
        check_frozen(out)
        state = inspect(out)
        if state['active_processes']:
            print('原批次刚刚启动，本次退出。',flush=True)
            return
        if state['completed'] == state['expected'] and not state['ambiguous']:
            print('所有单元已完成，不重复运行。',flush=True)
            return
        archive = archive_interrupted(out,state)
        print(f'已保留{state["completed"]}个完成单元；归档{len(state["interrupted"])}个中断单元。',flush=True)
        print('归档记录：'+str(archive/'resume_manifest.json'),flush=True)
        if state['retained_failures']:
            print('其他失败不会自动重试：'+json.dumps(state['retained_failures'],ensure_ascii=False),flush=True)
        print('续跑采用原冻结预算和资源门槛；中断单元从头求解，不恢复搜索树。',flush=True)
        child = subprocess.Popen([sys.executable,'-X','utf8','-u',str(ENTRY),'run','--campaign',str(out)],cwd=ROOT)
        try:
            code = child.wait()
        except KeyboardInterrupt:
            print('\n已收到Ctrl+C，等待原监督器保存中断记录并退出……',flush=True)
            try:
                code = child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                raise RuntimeError('原监督器尚未退出；再次续跑前先检查进程，不删除锁。')
        if code:
            raise SystemExit(code)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('action',choices=('inspect','run'))
    args = parser.parse_args()
    assert CAMPAIGN.resolve().is_relative_to((ROOT/'JMS-version/results').resolve())
    if args.action == 'inspect':
        print(json.dumps(compact(inspect(CAMPAIGN)),ensure_ascii=False,indent=2))
    else:
        run(CAMPAIGN)


if __name__=='__main__':
    main()
