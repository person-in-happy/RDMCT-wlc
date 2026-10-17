"""Five clean/dirty-hand perturbations, with immutable protocol and cell resume."""
from pathlib import Path
from dataclasses import asdict,replace
import argparse,json
from model import Config
from run_experiments import ports,solve,dump,assets
from run_matched_supplement import output_lock,archive_incomplete
from validate import validate

def completed(dest):
    """SPBS perturbation runs do not use an external common warm start."""
    path=Path(dest)/'result.json'
    if not path.exists():return False
    try:
        data=json.loads(path.read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError:return False
    if data.get('config',{}).get('vtr_hand_policy')!='clean_dirty':
        raise RuntimeError('Saved perturbation uses a different VTR hand policy: '+str(dest))
    if not validate(data)['valid']:
        raise RuntimeError('Saved perturbation failed independent physical validation: '+str(dest))
    return True

def run(output):
    out=Path(output)
    with output_lock(out):
        protocol=dict(assets=assets(),time_limit=300,initialization_budget=20,seed=1,vtr_hand_policy='clean_dirty')
        frozen=out/'protocol.json'
        if frozen.exists() and json.loads(frozen.read_text())!=protocol:raise ValueError('Protocol changed; choose a new output root')
        dump(frozen,protocol)
        base=Config(ports(8,'mixed'),cleaning_interval=3)
        cases={'process_090':replace(base,full_time=162,mix_time=81),'process_110':replace(base,full_time=198,mix_time=99)}
        cases.update({f'dummy_{n:02d}':replace(base,dummy_count=n) for n in (4,6,10)})
        for name,cfg in cases.items():
            dest=out/name
            if completed(dest):continue
            if dest.exists():archive_incomplete(out,dest)
            config=out/(name+'.json');dump(config,asdict(cfg))
            solve(config,dest,time_limit=300,stage2_limit=0,seed=1,method='scip',initialization='spbs',initialization_budget=20)
            if not completed(dest):raise RuntimeError('No validated result: '+str(dest))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)
