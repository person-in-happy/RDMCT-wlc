"""Foreground lower-RSS campaigns; preserve old results as separate strata."""
from pathlib import Path
from types import SimpleNamespace
import argparse,json,subprocess,sys,shutil,collections
import psutil
import evidence_supplement as e
from memory_policy import SCIP_MB,PROCESS_MB,RESERVE_MB,WAIT_SECONDS,required_memory

HERE=Path(__file__).resolve().parent
EQUIVALENT_FILES=('model.py','validate.py','grippers.py','seed.py','joint_algorithms.py',
    'joint_pairing_model.py','joint_chamber_cycle_model.py','reference_completion.py','supplement_protocol.py')


def require_idle(parent):
    for p in psutil.process_iter(['pid','name','cmdline']):
        try:
            cmd=p.info['cmdline'] or []
            if p.pid==__import__('os').getpid() or 'python' not in (p.info['name'] or '').lower() or '--campaign' not in cmd:continue
            path=Path(cmd[cmd.index('--campaign')+1])
            if not path.is_absolute():path=Path(p.cwd())/path
            if path.resolve()==parent:
                raise RuntimeError(f'Parent campaign still active (PID {p.pid}). Press Ctrl+C in its foreground terminal and wait for all workers to exit; saved results stay intact.')
        except (psutil.NoSuchProcess,psutil.ZombieProcess):continue
        except psutil.AccessDenied as exc:raise RuntimeError('Cannot confirm parent is idle') from exc


def split_mode_groups(cells,completed):
    groups=collections.defaultdict(list)
    for cell in cells:
        parts=cell['case'].split('_')
        if len(parts)!=4 or parts[0]!='n24' or parts[2] not in ('4x1','2x2','mixed') or cell['variant']!='joint':
            raise ValueError('Unexpected mode24 comparison matrix')
        groups[(parts[0],parts[1],parts[3],cell['seed'])].append(cell)
    retained=set()
    for group in groups.values():
        if len(group)!=3:raise ValueError('Each mode comparison must have all three recipes')
        if all(c['id'] in completed for c in group):retained.update(c['id'] for c in group)
    return [c for c in cells if c['id'] not in retained],sorted(retained)


def parent_plan(parent,suite):
    require_idle(parent)
    if suite!='mode24':raise ValueError('Parent continuation is currently supported for mode24 only')
    spec=e.read(parent/'campaign.json');meta=e.read(parent/'supplement.json')
    if spec['suite']!=suite or meta['campaign_sha256']!=e.digest(parent/'campaign.json'):
        raise ValueError('Parent campaign contract mismatch')
    for name in EQUIVALENT_FILES:
        matches=[sha for path,sha in spec['assets'].items() if Path(path).name==name]
        if matches!=[e.digest(HERE/name)]:raise ValueError('Physical model or initialization changed: '+name)
    old=e.ROOT/'JMS-version/model2_compact_20261025/evidence_supplement.py'
    if e.digest(old)!=meta['contract']['launcher_sha256']:raise ValueError('Parent launcher changed')
    result=subprocess.run([sys.executable,'-X','utf8','-u',str(old),'audit','--campaign',str(parent)],cwd=e.ROOT,capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise RuntimeError('Parent audit failed: '+result.stderr[-3000:])
    reports=[json.loads(line)['report'] for line in result.stdout.splitlines() if line.startswith('{') and '"report"' in line]
    if not reports:raise RuntimeError('Parent audit did not produce a report')
    report=Path(reports[-1]);audit=e.read(report)
    cells,retained=split_mode_groups(spec['cells'],{r['id'] for r in audit['rows']})
    return spec,cells,dict(parent=str(parent),parent_campaign_sha256=e.digest(parent/'campaign.json'),
        parent_audit=str(report),parent_audit_sha256=e.digest(report),retained_external_cells=retained,
        rerun_partial_group_cells=sorted({r['id'] for r in audit['rows']}-set(retained)),
        pending_cells=[c['id'] for c in cells],
        interpretation='Retained results stay in the parent resource stratum. Do not pool runtime or cross-budget seed statistics. Partial mode groups rerun in full.')


def prepare(out,suite,parent=None):
    if out.exists():
        spec,_=e.checked(out)
        if spec['suite']!=suite:raise ValueError('Suite mismatch')
        transition=out/'continuation.json'
        if parent is not None and (not transition.exists() or e.read(transition)['parent']!=str(parent)):
            raise ValueError('Parent differs from frozen continuation')
        return
    plan=parent_plan(parent,suite) if parent is not None else None
    if plan and not plan[1]:raise RuntimeError('All parent comparison groups are complete; no continuation needed')
    e.prepare(SimpleNamespace(campaign=str(out),suite=suite,memory_mb=SCIP_MB,jobs=1))
    if plan:
        e.dump(out/'preparation_pending.json',dict(parent=str(parent),started_utc=e.stamp()))
        old,cells,transition=plan;spec=e.read(out/'campaign.json')
        for key in ('time_limit','wall_limit','spbs_budget','seeds','cut_profile'):
            if spec[key]!=old[key]:raise ValueError('Cannot reuse references across different '+key)
        spec['cells']=cells
        keys={c['case'] for c in cells}
        spec['case_hashes']={k:v for k,v in spec['case_hashes'].items() if k in keys}
        for key in spec['case_hashes']:
            if spec['case_hashes'][key]!=old['case_hashes'][key]:raise ValueError('Parent configuration differs: '+key)
            e.reference_receipt(parent,key,old)
            src=parent/'references'/key;dst=out/'references'/key;dst.mkdir(parents=True)
            cert=e.read(src/'certificate.json')
            for name in list(cert['files'])+['certificate.json']:
                if Path(name).name!=name:raise ValueError('Unexpected reference path')
                shutil.copy2(src/name,dst/name)
            e.reference_receipt(out,key,spec)
        e.dump(out/'continuation.json',transition)
        spec['continuation_sha256']=e.digest(out/'continuation.json')
        e.dump(out/'campaign.json',spec)
        meta=e.read(out/'supplement.json');meta['campaign_sha256']=e.digest(out/'campaign.json');e.dump(out/'supplement.json',meta)
        (out/'preparation_pending.json').unlink()
        print(f"CONTINUATION retained={len(transition['retained_external_cells'])} in old protocol; new={len(cells)}; partial_group_reruns={len(transition['rerun_partial_group_cells'])}",flush=True)
    e.checked(out)


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('action',choices=('start','prepare','resume','audit','status','check'))
    p.add_argument('--suite',choices=e.SUITES)
    p.add_argument('--campaign')
    p.add_argument('--parent',help='Stopped compact mode24 campaign; retain only complete three-mode groups')
    a=p.parse_args()
    print(json.dumps(dict(scip_memory_mb=SCIP_MB,process_rss_limit_mib=PROCESS_MB,reserve_mib=RESERVE_MB,
        start_required_mib=required_memory({'memory_mb':SCIP_MB,'process_memory_mb':PROCESS_MB}),
        available_mib=psutil.virtual_memory().available/1024**2,ram_wait_seconds=WAIT_SECONDS)),flush=True)
    if a.action=='check':return
    if not a.campaign:p.error('--campaign is required')
    out=e.campaign_path(a.campaign)
    if a.action in ('prepare','start'):
        if not a.suite:p.error('--suite is required')
        parent=e.campaign_path(a.parent) if a.parent else None
        prepare(out,a.suite,parent)
        if a.action=='start':e.preflight(out);e.run(out,resume=True)
    elif a.action=='resume':
        if a.parent:p.error('--parent belongs only to start/prepare')
        if not (out/'preflight_passed.json').exists():e.preflight(out)
        e.run(out,resume=True)
    elif a.action=='audit':e.audit(out)
    else:
        from experiment_console import display
        e.checked(out);display(out,1)


if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError) as exc:
        print('STOP: '+str(exc),file=sys.stderr,flush=True);raise SystemExit(2)
