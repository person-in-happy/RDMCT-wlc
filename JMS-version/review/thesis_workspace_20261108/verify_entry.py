"""Build/check saved assignments only. Never calls optimize or run."""
from pathlib import Path
import argparse,sys,time,json,hashlib
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'JMS-version/tools'))
import thesis_gap_experiments as g

base=Path(__file__).resolve().parent/('entry_checks_'+str(time.time_ns()))
base.mkdir()
checks=[]
for suite in ('encoding','structure','cleanup','spbs','rhythm_search'):
    a=argparse.Namespace(suite=suite,source_campaign=None,time_limit=300,stage2_limit=60,min_available_fraction=.10,wall_limit=1800)
    out=base/suite
    g.prepare(a,out)
    spec=g.checked(out)
    st=spec['settings']
    assert st['memory_mb']>=1e12 and st['process_memory_mb'] is None
    assert st['memory_policy']=='scip_native_unlimited_system_available_fraction'
    assert len(spec['cells'])==dict(encoding=24,structure=36,cleanup=12,spbs=24,rhythm_search=9)[suite]
    if suite=='rhythm_search':continue
    # Each D case and each representation is checked without an optimization call.
    for c in spec['cells']:
        if c['seed']!=1 or (suite=='structure' and c['arm']!='fixed') or (suite=='spbs' and c['arm']!='spbs'):continue
        g.worker(out,c['id'],check_only=True)
        checks.append(dict(suite=suite,cell=c['id'],passed=True))
    assert g.summarize(out)['complete']==0
try:
    g.checked(g.RESULTS/'gap_d_structure_20261108_r1')
except RuntimeError as e:
    assert 'only accepts new uncapped' in str(e)
else:raise AssertionError('Must reject fixed-memory campaign')
try:
    g.plan(argparse.Namespace(suite='rhythm',source_campaign=str(base/'rhythm_search')))
except ValueError as e:
    assert 'Finish all witness-search' in str(e)
else:raise AssertionError('Must reject uncompleted witness search')
report=dict(checked_inputs=checks,solver_started=False,backend=str(g.BACKEND),driver_sha256=g.digest(Path(g.__file__)),scip_default_memory=st['memory_mb'],process_memory_cap=None,old_campaign_rejected=True,incomplete_rhythm_rejected=True,check_directory=str(base))
g.dump(Path(__file__).resolve().parent/'entry_verification.json',report)
print('CHECKED',len(checks),'INPUTS; NO OPTIMIZATION')
