"""Foreground, bounded equivalence/resource probe, not a formal comparison."""
from pathlib import Path
import argparse,json,time,sys,psutil,hashlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
p=argparse.ArgumentParser(__doc__)
p.add_argument('--implementation',choices=('baseline','compact'),default='compact')
p.add_argument('--n',type=int,default=1)
p.add_argument('--recipe',choices=('4x1','2x2','mixed'),default='2x2')
p.add_argument('--source',choices=('single','dual'),default='dual')
p.add_argument('--seconds',type=float,default=60)
p.add_argument('--memory-mb',type=int,default=14000)
p.add_argument('--output',required=True)
p.add_argument('--witness')
p.add_argument('--free-optimum',action='store_true')
p.add_argument('--lift',action='store_true')
p.add_argument('--build-only',action='store_true')
a=p.parse_args()
lib=ROOT/'JMS-version/joint_model' if a.implementation=='baseline' else HERE
# Baseline must import the unchanged root pairing/cycle blocks.
sys.path[:0]=[str(lib),str(ROOT)] if a.implementation=='baseline' else [str(HERE),str(ROOT)]
from model import Config,Integrated
from run_experiments import ports,assets,finite
from supplement_protocol import balanced_reference
from seed import constrain_seed
from validate import validate

out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
def dump(name,d):
    (out/name).write_text(json.dumps(finite(d),ensure_ascii=False,indent=2),encoding='utf-8')
def memory():
    info=psutil.Process().memory_info()
    return dict(rss_mib=info.rss/1024**2,peak_rss_mib=getattr(info,'peak_wset',info.rss)/1024**2)
cfg=Config(ports(a.n,a.recipe),source=a.source,cleaning_interval=3)
reference=json.loads(Path(a.witness).read_text(encoding='utf-8')) if a.witness else balanced_reference(cfg)
assert validate(reference)['valid']
dump('input.json',reference)
print('BUILD '+a.implementation+f' n={a.n} {a.recipe} {a.source}',flush=True)
t=time.monotonic();x=Integrated(cfg);m=x.model
record=dict(implementation=a.implementation,n=a.n,recipe=a.recipe,source=a.source,
    assets=assets(),build_seconds=time.monotonic()-t,dimensions=x.original_dimensions,
    safe_bounds=x.safe_bounds,restricted=x.bounded,memory_mb=a.memory_mb,**memory())
dump('build.json',record);print(json.dumps(record|{'assets':'recorded'}),flush=True)
if a.build_only:
    m.freeProb();raise SystemExit(0)
m.setIntParam('parallel/maxnthreads',1);m.setIntParam('lp/threads',1)
m.setRealParam('limits/memory',a.memory_mb);m.setRealParam('limits/time',a.seconds)
if a.lift:
    from reference_completion import complete_reference
    initial,values,levels,completion=complete_reference(x,reference,a.memory_mb,20)
    dump('completion.json',completion);dump('spbs_levels.json',levels)
    sol=m.createSol()
    for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
    result=x.result(solution=sol);m.freeSol(sol)
    dump('completed_witness.json',result)
else:
    fixed=constrain_seed(x,reference);m.setObjective(0);m.setLogfile(str(out/'solver.log'));m.optimize()
    assert m.getNSols(),str(m.getStatus())
    assert m.checkSol(m.getBestSol(),completely=True,original=True)
    result=x.result();assert validate(result)['valid'];dump('completed_witness.json',result)
    values={v.name:m.getSolVal(m.getBestSol(),v) for v in m.getVars(transformed=False)}
    m.freeTransform()
    if a.implementation=='compact':
        from seed import release_fixed
        release_fixed(m,fixed)
    else:
        for v,lb,ub in fixed:m.chgVarLb(v,lb);m.chgVarUb(v,ub)
sol=m.createSol()
for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
assert m.checkSol(sol,completely=True,original=True)
if a.free_optimum:
    m.addSol(sol);m.setObjective(x.primary_objective);m.setRealParam('limits/time',a.seconds);m.optimize()
    result=x.result();assert validate(result)['valid'];assert m.checkSol(m.getBestSol(),completely=True,original=True)
    dump('result.json',result)
else:m.freeSol(sol)
record.update(elapsed_seconds=time.monotonic()-t,cmax=result['cmax'],status=result['status'],
    original_model_check=True,physical=validate(result),fixed_released_check=True,**memory())
dump('finished.json',record);print('VERIFIED '+json.dumps({k:v for k,v in record.items() if k not in ('assets','physical')}),flush=True)
m.freeProb()
