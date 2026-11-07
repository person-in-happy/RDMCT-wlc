"""Matched supplements with cell-level resume, preserved attempts and OS locking."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
import argparse,json,os
from run_experiments import solve,assets,digest,dump

@contextmanager
def output_lock(out):
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.run.lock').open('a+b') as f:
        if f.tell()==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as e:raise RuntimeError('This supplement is already running') from e
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def completed(dest):
    try:
        r=json.loads((dest/'result.json').read_text(encoding='utf-8-sig'))
        w=json.loads((dest/'warm_start_check.json').read_text(encoding='utf-8-sig'))
    except (FileNotFoundError,json.JSONDecodeError):return False
    if not r.get('validation',{}).get('valid') or not w.get('accepted'):
        raise RuntimeError('Completed cell failed validation or common warm-start check: '+str(dest))
    return True

def archive_incomplete(out,dest):
    root=out.resolve();target=dest.resolve()
    if dest.is_symlink() or target.parent!=root:raise RuntimeError('Unsafe interrupted run path')
    archive=root/'interrupted_attempts'/(dest.name+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if not archive.resolve().is_relative_to(root):raise RuntimeError('Unsafe archive path')
    archive.parent.mkdir(exist_ok=True);dest.rename(archive)
    print('PRESERVED '+str(archive),flush=True)

def run(reference,output,stage,budget=300,resume=False):
    if budget<=0:raise ValueError('Time limit must be positive')
    ref=Path(reference);out=Path(output)
    with output_lock(out):return run_locked(ref,out,stage,budget,resume)

def run_locked(ref,out,stage,budget,resume):
    manifest=json.loads((ref/'manifest.json').read_text(encoding='utf-8-sig'))
    if manifest['assets']!=assets():raise RuntimeError('Reference code inventory changed; prepare a new common reference')
    cert=json.loads((ref/'certificate.json').read_text(encoding='utf-8-sig'))
    if not cert['valid']:raise RuntimeError('Common reference is not validated')
    warm=json.loads((ref/'variables.json').read_text(encoding='utf-8-sig'))
    if warm['config_sha256']!=digest(ref/'config.json'):raise RuntimeError('Common input configuration changed')
    protocol=dict(reference=str(ref.resolve()),reference_sha256=digest(ref/'reference.json'),warm_sha256=digest(ref/'variables.json'),assets=assets(),budget=budget,seed=1,training_seed=1,initialization='shared_offline_reference',scope='Instance-specific paired comparison; initialization cost reported separately')
    f=out/'protocol.json'
    if f.exists():
        if json.loads(f.read_text(encoding='utf-8'))!=protocol:raise RuntimeError('Matched protocol changed; choose a new output')
    else:dump(f,protocol)
    cells={'structure':[('scip_fixed', 'scip',True,budget,0),('scip_joint','scip',False,budget,0)],'refinement':[('scip_refined','scip',False,budget*.9,budget*.1)],'algorithm':[('hem_joint','hem',False,budget,0),('proposed_joint','proposed',False,budget,0)]}[stage]
    if stage!='structure' and not completed(out/'scip_joint'):raise RuntimeError('Run structure first; its joint SCIP cell supplies the reused baseline')
    progress_file=out/'progress.json'
    progress=json.loads(progress_file.read_text(encoding='utf-8')) if progress_file.exists() else {'cells':{}}
    def record(name,status,**extra):
        progress['cells'][name]=dict(status=status,updated=datetime.now().isoformat(),**extra);dump(progress_file,progress)
    for name,method,fixed,t1,t2 in cells:
        dest=out/name
        if completed(dest):
            record(name,'complete',reused=True);print('REUSE '+str(dest),flush=True);continue
        if dest.exists():
            if not resume:raise RuntimeError('Incomplete cell retained; rerun with --resume: '+str(dest))
            archive_incomplete(out,dest)
        record(name,'running')
        try:
            summary=solve(ref/'config.json',dest,time_limit=t1,stage2_limit=t2,seed=1,warm_start=ref/'variables.json',fixed=ref/'reference.json' if fixed else None,memory_mb=24000,method=method,initialization='none',initialization_budget=0)
            if not completed(dest):raise RuntimeError('Cell did not save a validated completed result')
            record(name,'complete',reused=False);print(json.dumps(summary),flush=True)
        except BaseException as e:
            record(name,'interrupted_or_failed',reason=str(e));raise
    print('Stage complete. Resume skips validated cells; interrupted cells restart without restoring a SCIP search tree.',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',required=True);p.add_argument('--output',required=True);p.add_argument('--stage',choices=['structure','refinement','algorithm'],required=True);p.add_argument('--time-limit',type=float,default=300);p.add_argument('--resume',action='store_true');a=p.parse_args();run(a.reference,a.output,a.stage,a.time_limit,a.resume)
