"""Complete a candidate in the ORIGINAL full-capacity MILP; feasibility only."""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'JMS-version/joint_model'))
from model import Config,Integrated
from seed import constrain_seed
from validate import validate
from run_experiments import dump,digest,assets,finite

def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--memory-mb',type=float,default=6000)
    a=p.parse_args();source=Path(a.source).resolve();out=Path(a.output).resolve()
    data=json.loads(source.read_text(encoding='utf-8-sig'))
    replay=validate(data)
    if not replay['valid']:raise ValueError(replay['errors'])
    cfg=Config(**data['config'])
    if cfg.max_pairs or cfg.max_cycles:raise ValueError('Original configuration required')
    out.mkdir(parents=True,exist_ok=False)
    print('BUILD ORIGINAL FULL MODEL for candidate certification',flush=True)
    x=Integrated(cfg);m=x.model;m.hideOutput(False)
    m.setIntParam('parallel/maxnthreads',1);m.setRealParam('limits/memory',a.memory_mb)
    m.setRealParam('limits/time',120);m.setLogfile(str(out/'solver.log'))
    constrain_seed(x,data);m.setObjective(0,'minimize');m.optimize()
    accepted=bool(m.getNSols() and m.checkSol(m.getBestSol(),printreason=False,completely=True))
    completion=x.result();recheck=validate(completion)
    record=dict(source=str(source),source_sha256=digest(source),assets=assets(),
                full_candidate_space=not x.bounded,dimensions=x.original_dimensions,
                status=str(m.getStatus()),accepted=accepted and recheck['valid'],
                physical=recheck,cmax=data['cmax'],scope='Original-model feasibility only; NOT optimality')
    dump(out/'certificate.json',finite(record))
    if not record['accepted']:raise RuntimeError('Original-model candidate completion failed')
    dump(out/'completion.json',finite(completion))
    print('ORIGINAL MODEL ACCEPTED Cmax='+str(data['cmax']),flush=True)
    m.freeProb()

if __name__=='__main__':main()
