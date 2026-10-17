"""Resume frozen campaigns with separately recorded strict timing recovery."""
import argparse,json
from pathlib import Path
from types import SimpleNamespace
import run_experiments as original
from recover_timing import run as recover
from validate import validate
from run_matched_supplement import archive_incomplete

def run_locked(a):
    out=Path(a.campaign).resolve();manifest=json.loads((out/'campaign.json').read_text())
    if manifest['assets']!=original.assets():raise RuntimeError('Frozen code differs')
    for method,record in manifest.get('policy_records',{}).items():
        if record!=original.policy_record(method,manifest.get('training_seed',1)):raise RuntimeError('Frozen policy differs')
    settings=json.loads((out/'execution.json').read_text())
    if settings['export_only']:raise ValueError('Recovery requires solved experiments')
    protocol=dict(assets=original.assets(),runner_sha256=original.digest(Path(__file__)),recovery_sha256=original.digest(Path(__file__).with_name('recover_timing.py')),settings=settings,recovery_time_limit=30)
    recovery_root=out/'timing_recoveries';recovery_root.mkdir(exist_ok=True)
    pf=recovery_root/'protocol.json'
    if pf.exists() and json.loads(pf.read_text())!=protocol:raise RuntimeError('Recovery protocol changed')
    original.dump(pf,protocol)
    for cell in manifest['cells']:
        if original.digest(out/cell['config'])!=cell['sha256']:raise RuntimeError('Frozen input differs')
    for cell in manifest['cells']:
        dest=out/'runs'/cell['id'];result=dest/'result.json'
        if result.exists():
            if not validate(json.loads(result.read_text()))['valid']:raise RuntimeError('Saved result failed replay: '+str(dest))
            print('REUSE '+cell['id'],flush=True);continue
        phase=dest/'phase1.json';values=dest/'variables_phase1.json'
        if dest.exists() and not (phase.exists() and values.exists()):archive_incomplete(out,dest)
        if not dest.exists():
            print('START '+cell['id'],flush=True)
            try:
                original.solve(out/cell['config'],dest,settings['time_limit'],settings['stage2_limit'],cell['seed'],False,memory_mb=settings['memory_mb'],method=cell.get('method','scip'),training_seed=manifest.get('training_seed',1),fixed='constructed' if cell.get('formulation')=='fixed' else None,initialization=settings['initialization'],initialization_budget=settings['initialization_budget'])
            except RuntimeError as exc:
                if str(exc)!='Primary physical validation failed; inspect phase1.json':raise
            else:continue
        if not (phase.exists() and values.exists()):raise RuntimeError('Missing recovery assets')
        print('RECOVER '+cell['id'],flush=True)
        recover(dest,recovery_root/cell['id'],30)
        # Never create result.json in the original run or replace its benchmark.
        print('RECOVERED_WITNESS_ONLY '+cell['id'],flush=True)
    print('Completed; timing_recoveries are separate feasible witnesses, not fixed-budget benchmarks.',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',required=True);a=p.parse_args()
    original._campaign_locked=run_locked
    original.campaign(a)
