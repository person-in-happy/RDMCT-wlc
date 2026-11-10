"""Read-only evidence and full-model replay. Never invokes optimize."""
from pathlib import Path
from dataclasses import asdict
import sys,json,hashlib
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'cie/code'))
import run_current_jms_experiments as c
sys.path.insert(0,str(ROOT/'JMS-version/tools'))
import journal_support_experiments as j
digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
source=ROOT/'JMS-version/JMS_Review_CN.tex'
manifest=j.read(HERE/'migration_manifest.json')
assert digest(source)==manifest['jms_source_sha256']
cases={r['case']:asdict(j.base.backend.Config(**{k:v for k,v in r.items() if k not in ('case','n','nfull')})) for r in c.case_plan('generalization')}
assert json.dumps(cases,sort_keys=True)==json.dumps(dict(j.test_cases()),sort_keys=True)
evidence=j.read(ROOT/'JMS-version/revisions/20261109_journal_results/evidence.json')
for p,h in evidence['hashes'].items():
    assert digest(p)==h,p
print('evidence hashes',len(evidence['hashes']),flush=True)
witness=j.base.SMALL/'runs/n1_H2_2x2_dual__s1__scip'
rows=[]
for phase,variables in [('phase1','variables_phase1'),('result','variables')]:
    d=j.read(witness/(phase+'.json'))
    audit=j.checked_result(d,witness/(variables+'.json'))
    rows.append(dict(phase=phase,cmax=d['cmax'],audit=audit,source_sha256=digest(witness/(phase+'.json'))))
    print('replayed',phase,d['cmax'],flush=True)
for fig in manifest['figures']:
    assert digest(ROOT/fig['source'])==fig['sha256']==digest(ROOT/'cie/products'/fig['file'])
unchanged=[]
for filename in ('rdmct_cie_analysis_focused.tex','rdmct_cie_draft.tex'):
    assert digest(HERE/'before'/filename)==digest(ROOT/'cie/products'/filename)
    unchanged.append(filename)
result=dict(jms_source_sha256=digest(source),experiment_files_hash_checked=len(evidence['hashes']),
            identical_generalization_configs=len(cases),witness_replays=rows,unchanged_english=unchanged,solver_started=False)
j.dump(HERE/'evidence_verification.json',result)
