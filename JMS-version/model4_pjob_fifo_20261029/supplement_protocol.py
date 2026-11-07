"""Prepare a two-chamber reference and common warm start without changing frozen runners."""
from pathlib import Path
from dataclasses import asdict,replace
from collections import defaultdict
import argparse,copy,json,time
from model import Config,Integrated,products_from_load_ports
from seed import construct,constrain_seed,release_fixed
from validate import validate
from run_experiments import assets,digest,dump,finite


def balanced_reference(cfg):
    """Assign consecutive same-recipe product pairs by nominal chamber workload.

    This is a deterministic baseline, not an optimal dispatching policy. Timing
    is initially serial and is optimized by the fixed-structure comparison.
    """
    return construct(cfg,balanced=True)


def prepare(config,output):
    started=time.monotonic();config=Path(config);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    cfg=Config(**json.loads(config.read_text(encoding='utf-8-sig')))
    if cfg.max_pairs or cfg.max_cycles:raise ValueError('Use full candidate bounds for this comparison')
    data=balanced_reference(cfg);dump(out/'reference.json',data);dump(out/'config.json',asdict(cfg))
    x=Integrated(cfg);m=x.model;fixed=constrain_seed(x,data);m.setObjective(0,'minimize');m.setRealParam('limits/time',30);m.setRealParam('limits/memory',24000);m.optimize()
    if not m.getNSols():raise RuntimeError('Warm-start completion failed; reference.json retained')
    sol=m.getBestSol();values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
    completed=x.result();completed['validation']=validate(completed)
    if not completed['validation']['valid']:raise RuntimeError(completed['validation']['errors'])
    m.freeTransform()
    release_fixed(m,fixed)
    sol=m.createSol()
    for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
    accepted=m.checkSol(sol,printreason=False,completely=True);m.freeSol(sol)
    if not accepted:raise RuntimeError('Initial assignment failed the released full model')
    dump(out/'variables.json',dict(values=values,config_sha256=digest(out/'config.json'),scope='Common initial assignment for fixed and unrestricted comparison'))
    dump(out/'certificate.json',finite(dict(valid=True,cmax=data['cmax'],chambers=sorted(set(p['chamber'] for p in data['pairs'])),dimensions=x.original_dimensions,physical=completed['validation'],seconds=time.monotonic()-started)))
    dump(out/'manifest.json',dict(assets=assets(),protocol_sha256=digest(Path(__file__)),source_config_sha256=digest(config)))
    m.freeProb();return dict(output=str(out),cmax=data['cmax'],valid=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(prepare(a.config,a.output)))
