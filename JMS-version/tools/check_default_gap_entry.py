import sys,json,argparse,time
from pathlib import Path
sys.path.insert(0,'JMS-version/tools')
import default_gap_experiments as g
base=g.RESULTS/'gap_entrychecks_20261108_v2'
base.mkdir(exist_ok=False)
checks=[]
for suite in ('encoding','structure','cleanup','spbs','rhythm_search'):
    a=argparse.Namespace(suite=suite,source_campaign=None,time_limit=300,stage2_limit=60,memory_mb=4096,process_memory_mb=6144,wall_limit=1800)
    out=base/suite
    g.prepare(a,out)
    spec=g.checked(out)
    assert len(spec['cells'])==dict(encoding=24,structure=36,cleanup=12,spbs=24,rhythm_search=9)[suite]
    if suite=='rhythm_search':
        assert all('4x1_dual' not in c['case'] for c in spec['cells'])
        continue
    for c in spec['cells']:
        if c['seed']!=1 or (suite=='structure' and c['arm']!='fixed') or (suite=='spbs' and c['arm']!='spbs'):
            continue
        g.worker(out,c['id'],check_only=True)
        checks.append(dict(suite=suite,cell=c['id'],passed=True))
    assert g.summarize(out)['complete']==0
report=dict(checked_inputs=checks,solver_started=False,backend=str(g.BACKEND),driver_sha256=g.digest(Path(g.__file__)))
g.dump(base/'verification.json',report)
print('CHECKED',len(checks),'INPUTS; NO OPTIMIZATION')
