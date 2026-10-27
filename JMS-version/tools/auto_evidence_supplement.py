"""Select memory once for new campaigns; retain the original frozen executor."""
from pathlib import Path
import argparse,json,math,shutil,sys
import psutil
import evidence_supplement as e
from supplement_memory_guard import require_unfailed_budget


def memory_gate(cases,settings,memory_mb):
    require_unfailed_budget(e.ROOT/'JMS-version/results',cases,e.inventory(),settings,memory_mb)


def allocation(available_mib,jobs,cap_mb):
    if not math.isfinite(available_mib) or available_mib<=0 or jobs<1 or cap_mb<1:
        raise ValueError('Invalid available RAM, jobs or cap')
    # Keep 10% of currently available RAM for fluctuations, in addition to
    # the original 2048 MiB reserve and 1.15 worker RSS allowance.
    ceiling=(0.9*available_mib-2048)/(1.15*jobs)
    selected=min(cap_mb,math.floor(ceiling/256)*256)
    if selected<1024:
        raise RuntimeError('Available RAM cannot support at least 1024 MiB per worker with reserves; wait or reduce Jobs')
    return dict(policy='available_ram_v1',available_mib=available_mib,jobs=jobs,
                cap_mb=cap_mb,memory_mb=selected,reserve_mib=2048,
                worker_rss_factor=1.15,available_fraction=0.9,rounding_mib=256,
                minimum_mb=1024,required_mib=selected*1.15*jobs+2048)


def prepare(args):
    out=e.campaign_path(args.campaign)
    if out.exists():
        contract=e.read(out/'supplement.json')['contract']
        if contract['suite']!=args.suite:raise RuntimeError('Suite differs from frozen campaign')
        # Never recalculate resources from today's RAM for an existing campaign.
        settings=contract['settings']
        if args.memory_mb is None:args.memory_mb=settings['memory_mb']
        if args.jobs is None:args.jobs=settings['jobs']
        e.prepare(args)
        print('REUSE frozen memory: '+str(settings['memory_mb'])+' MiB/worker',flush=True)
        return out
    defaults=e.defaults(args.suite)
    if args.jobs is None:args.jobs=defaults['jobs']
    if args.memory_mb is None:
        record=allocation(psutil.virtual_memory().available/1024**2,args.jobs,defaults['memory_mb'])
        args.memory_mb=record['memory_mb']
        print('AUTO MEMORY '+json.dumps(record),flush=True)
    else:
        record=dict(policy='explicit',memory_mb=args.memory_mb,jobs=args.jobs,
                    available_mib=psutil.virtual_memory().available/1024**2)
    record.update(selected_utc=e.stamp(),selector_sha256=e.digest(Path(__file__)),
                  note='Frozen per campaign; not proof that the full model fits this budget')
    cases,_=e.matrix(args.suite)
    memory_gate(cases,defaults,args.memory_mb)
    e.prepare(args)
    e.dump(out/'memory_selection.json',record)
    shutil.copy2(__file__,out/'frozen_code'/'auto_evidence_supplement.py')
    shutil.copy2(Path(__file__).with_name('supplement_memory_guard.py'),out/'frozen_code'/'supplement_memory_guard.py')
    return out


def main():
    # All later actions retain the original resource checks and failure policy.
    if len(sys.argv)>1 and sys.argv[1] not in ('prepare','start'):
        return e.main()
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('action',choices=('prepare','start'))
    p.add_argument('--suite',required=True,choices=e.SUITES)
    p.add_argument('--campaign',required=True)
    p.add_argument('--memory-mb',type=int,help='Omit for automatic selection on a NEW campaign')
    p.add_argument('--jobs',type=int)
    a=p.parse_args()
    if any(v is not None and v<=0 for v in (a.jobs,a.memory_mb)):p.error('Resource settings must be positive')
    out=prepare(a)
    if a.action=='start':
        spec=e.read(out/'campaign.json')
        if not (out/'preflight_passed.json').exists():
            cases={k:e.read(out/'configs'/f'{k}.json') for k in spec['case_hashes']}
            memory_gate(cases,spec,spec['memory_mb'])
        e.preflight(out);e.run(out)


if __name__=='__main__':main()
