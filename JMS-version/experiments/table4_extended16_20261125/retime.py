"""Tighten product-return time at the globally minimum process score in the packed structure."""
import sys
from blocks import (OUT,Path,configuration,replace,validate_native,normalize_schedule,sparse_witness,cell,
                    sha,read,write,metrics)
from model import Integrated


def run(h):
    cfg=replace(configuration(),cleaning_interval=h);out=OUT/f'H{h}'/'retime';out.mkdir(exist_ok=True,parents=True)
    if (out/'result.json').exists():return
    src=out.parent/'pack';ref=read(src/'result.json');doc=read(src/'schedule.json')
    assert ref['schedule_sha256']==sha(src/'schedule.json')
    small=replace(cfg,max_pairs=max(p['id'] for p in doc['pairs'])+1,max_cycles=max(c['index'] for c in doc['cycles'])+1)
    candidate=normalize_schedule(small,doc);vals=sparse_witness(small,candidate)
    x=Integrated(small);m=x.model
    cell.scip_settings(m,dict(n=16,seed=1,seconds=80,gap=0),out)
    m.setRealParam('numerics/feastol',1e-7)
    for v in m.getVars(transformed=False):
        if v.vtype()!='CONTINUOUS':
            k=round(vals.get(v.name,0));m.chgVarLb(v,k);m.chgVarUb(v,k)
    pairs={j['pair']:j for j in doc['jobs'] if j['product']}
    for k,j in pairs.items():
        diff=j['unload_start']-j['load_end']
        m.addCons(x.unload[k]['s']-x.load[k]['e']==diff)
    m.addCons(x.cmax<=doc['cmax']+1.e-7);m.setObjective(x.cmax,'minimize')
    print(f'H={h} original packed C {doc["cmax"]} s; one retiming stage, estimated 10–60 s',flush=True)
    m.optimize()
    sol=m.getBestSol()
    if sol is None:raise ValueError(m.getStatus())
    outdoc=x.result(solution=sol);status=str(m.getStatus());m.freeProb()
    outdoc=normalize_schedule(cfg,outdoc)
    f,r=validate_native(cfg,outdoc,out,dict(parent=ref['schedule_sha256'],fixed_structure_C_status=status))
    assert abs(f['secondary']-ref['lower'])<1.e-6
    write(out/'result.json',dict(upper=f['secondary'],lower=ref['lower'],metrics=f,H=h,rows=r['rows'],replay=r['replay'],
        source_sha256=sha(src/'result.json'),schedule_sha256=sha(out/'schedule.json'),assignment_sha256=sha(out/'assignment.json.gz'),
        scope='global minimum process score; product-return time of the shortest checked attaining schedule'))
    print(f"1/1 complete: C={f['cmax']}, fB={f['secondary']}, ETA 0s",flush=True)


if __name__=='__main__':run(int(sys.argv[1]))
