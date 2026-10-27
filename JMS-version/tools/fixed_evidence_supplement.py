"""Explicit fixed-memory entry; never selects a budget automatically."""
from pathlib import Path
import argparse,sys
import psutil
import evidence_supplement as e
from auto_evidence_supplement import prepare,memory_gate


def check_budget(out,memory_mb,jobs,suite,available_mib):
    if out.exists():
        c=e.read(out/'supplement.json')['contract']
        if c['suite']!=suite:raise ValueError('Suite differs from frozen campaign')
        if memory_mb is None:memory_mb=c['settings']['memory_mb']
        if jobs is None:jobs=c['settings']['jobs']
        if memory_mb!=c['settings']['memory_mb'] or jobs!=c['settings']['jobs']:
            raise ValueError('Frozen budget differs; use a new output directory')
    elif memory_mb is None:
        raise ValueError('New campaigns require explicit --memory-mb. Automatic allocation is disabled.')
    if jobs is None:jobs=1
    if memory_mb<=0 or jobs<=0:raise ValueError('Memory and jobs must be positive')
    required=memory_mb*1.15*jobs+2048
    if available_mib<required:
        raise RuntimeError(f'Fixed budget requires {required:.1f} MiB available RAM; observed {available_mib:.1f}. '
                           'No budget reduction or solver launch performed.')
    return memory_mb,jobs


def main():
    if len(sys.argv)>1 and sys.argv[1] not in ('start','prepare'):
        return e.main()
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('action',choices=('start','prepare'));p.add_argument('--campaign',required=True)
    p.add_argument('--suite',required=True,choices=e.SUITES)
    p.add_argument('--memory-mb',type=int);p.add_argument('--jobs',type=int)
    a=p.parse_args();out=e.campaign_path(a.campaign)
    a.memory_mb,a.jobs=check_budget(out,a.memory_mb,a.jobs,a.suite,psutil.virtual_memory().available/1024**2)
    # Explicitly populated memory means the compatibility helper cannot call allocation().
    out=prepare(a)
    if a.action=='start':
        spec=e.read(out/'campaign.json')
        if not (out/'preflight_passed.json').exists():
            cases={k:e.read(out/'configs'/f'{k}.json') for k in spec['case_hashes']}
            memory_gate(cases,spec,spec['memory_mb'])
        e.preflight(out);e.run(out)


if __name__=='__main__':main()
