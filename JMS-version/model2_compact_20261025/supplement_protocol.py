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
    products=products_from_load_ports(cfg.load_ports)
    assigned={c:[] for c in cfg.chambers};work={c:0 for c in cfg.chambers}
    for mode,duration in [('4x1',cfg.full_time),('2x2',2*cfg.mix_time)]:
        ws=[w for w in products if w.mode==mode]
        for i in range(0,len(ws),2):
            c=min(cfg.chambers,key=lambda c:(work[c],c));assigned[c]+=ws[i:i+2];work[c]+=duration
    template={'pairs':[],'cycles':[]}
    for c,ws in assigned.items():
        if not ws:continue
        ports={k:{'4x1':0,'2x2':0} for k in cfg.load_ports};targets=defaultdict(list)
        for w in ws:ports[f'LP{w.load_port}'][w.mode]+=1;targets[w.load_port,w.mode].append(w.identifier)
        local=replace(cfg,load_ports=ports,chambers=(c,));part=construct(local)
        mapping={}
        for w in products_from_load_ports(ports):mapping[w.identifier]=targets[w.load_port,w.mode].pop(0)
        offset=len(template['pairs'])
        for p in part['pairs']:
            p=copy.deepcopy(p);p['id']+=offset;p['members']=[mapping.get(w,w) for w in p['members']];template['pairs'].append(p)
        for q in part['cycles']:
            q=copy.deepcopy(q);q['pairs']=[p+offset for p in q['pairs']];q['front']+=offset;template['cycles'].append(q)
    result=construct(cfg,template)
    result['reference_policy']='Same-recipe product pairs, greedy nominal workload assignment across chambers; serial feasible timing seed'
    return result


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
