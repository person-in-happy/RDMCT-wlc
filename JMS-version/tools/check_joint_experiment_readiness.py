"""Audit the dedicated joint-model entry point; optional bounded physical smoke checks."""
from pathlib import Path
import argparse,ast,json,sys
ROOT=Path(__file__).resolve().parents[2]
HERE=ROOT/'JMS-version/joint_model'

def audit(verify=False):
    files=['model.py','validate.py','seed.py','run_experiments.py','joint_algorithms.py','reuse_legacy.py','retime_legacy.py']
    checks={}
    for name in files:
        p=HERE/name
        try:ast.parse(p.read_text(encoding='utf-8-sig'));checks[name]=True
        except (OSError,SyntaxError):checks[name]=False
    result=dict(entry_point=str(HERE/'run_experiments.py'),source_checks=checks,full_joint_experiment_ready=False,scope='Execution readiness only; publication claims require instance-specific evidence.',physical_smoke=[])
    if verify and all(checks.values()):
        sys.path.insert(0,str(HERE))
        from model import Config,Integrated
        from seed import construct,constrain_seed
        from validate import validate
        for source in ('single','dual'):
            for mode in ('4x1','2x2'):
                cfg=Config({'LP1':{mode:1},'LP2':{mode:1},'LP3':{},'LP4':{}},source=source,cleaning_interval=2)
                initial=construct(cfg);cfg.max_pairs=len(initial['pairs']);cfg.max_cycles=max(c['index'] for c in initial['cycles'])+1
                x=Integrated(cfg);m=x.model;constrain_seed(x,initial);m.setObjective(0,'minimize');m.setRealParam('limits/time',10);m.optimize()
                valid=bool(m.getNSols() and validate(x.result())['valid']);result['physical_smoke'].append(dict(source=source,mode=mode,valid=valid));m.freeProb()
        result['full_joint_experiment_ready']=all(c['valid'] for c in result['physical_smoke'])
    result['remaining_evidence']=['Independent small-instance optimum check','Matched joint/fixed and single/dual experiments under identical product input','Algorithm comparison on new joint-model instances; legacy lower bounds cannot transfer']
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--require-full',action='store_true');p.add_argument('--verify',action='store_true');a=p.parse_args()
    r=audit(a.verify or a.require_full);print(json.dumps(r,indent=2))
    if a.require_full and not r['full_joint_experiment_ready']:raise SystemExit(2)
