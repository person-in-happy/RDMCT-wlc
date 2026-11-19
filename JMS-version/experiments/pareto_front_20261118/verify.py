"""Independent HiGHS audit of final continuous open rectangles and physical witnesses."""
from pathlib import Path
import argparse
import time
import traceback
from importlib.metadata import version
import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp
from slices import Config, BACKEND, ROOT, TOL, digest, log, physical_metrics, read, save
from family import build,lift
from split_oracle import PATTERNS,SplitOracle

def highs_gap(m,aa,bb,r,h,seconds):
    t=m.addVar(lb=0,ub=1000,name='independent_gap')
    m.addCons(aa+t<=r);m.addCons(bb+t<=h);m.setObjective(t,'maximize')
    vs=m.getVars(transformed=False);idx={v.name:i for i,v in enumerate(vs)}
    rr=[];cc=[];vv=[];l=[];u=[]
    for i,c in enumerate(m.getConss(transformed=False)):
        assert c.getConshdlrName()=='linear'
        for n,a in m.getValsLinear(c).items():rr.append(i);cc.append(idx[n]);vv.append(a)
        lower=m.getLhs(c);upper=m.getRhs(c)
        l.append(lower if lower>-1e19 else -np.inf);u.append(upper if upper<1e19 else np.inf)
    problem=LinearConstraint(sparse.csc_matrix((vv,(rr,cc)),shape=(len(l),len(vs))),l,u)
    objective=-np.asarray([v.getObj() for v in vs])
    result=milp(objective,integrality=np.asarray([int(v.vtype()!='CONTINUOUS') for v in vs]),
                bounds=Bounds([v.getLbOriginal() for v in vs],[v.getUbOriginal() for v in vs]),constraints=problem,
                options={'time_limit':seconds,'mip_rel_gap':0})
    bound=getattr(result,'mip_dual_bound',None)
    ub=float(-bound) if bound is not None and np.isfinite(bound) else None
    return dict(status=int(result.status),message=result.message,max_t_upper=ub,
                excluded=bool(result.status==2 or (ub is not None and ub<=TOL)))

def verify(base,out):
    n2=base/'n2';meta=read(n2/'slices.json');cfg=Config(**meta['config'])
    for n,h in meta['backend_hashes'].items():assert digest(BACKEND/n)==h
    sets=[('pp',read(n2/'cert_pp/certificate.json')),('split',read(n2/'cert_split/certificate.json'))]
    assert all(cert['complete'] for _,cert in sets)
    edges=[];targets=[]
    for kind,cert in sets:
        for interval in cert['parts']:
            assert abs(interval['slope'])<=1e-8 and interval['certified']
            r,h=interval['right'],interval['intercept']
            targets.append((interval['left'],h))
            for pattern in (['PP'] if kind=='pp' else PATTERNS):
                if kind=='pp':
                    x=build(cfg,kind);m=x.model
                    row=highs_gap(m,x.cmax,x.secondary_objective,r,h,45)
                else:
                    oracle=SplitOracle(cfg,pattern,min(r+1e-7,528.00001),min(h+1e-7,376/3+.00001))
                    m=oracle.model
                    row=dict(excluded=True,status='infeasible_by_precedence') if oracle.impossible else highs_gap(m,oracle.avar,oracle.bvar,r,h,45)
                edges.append(dict(family=kind,pattern=pattern,right=r,height=h,**row))
                m.freeProb();log(out,f'verified {len(edges)}/17 rectangles, failed={sum(not e["excluded"] for e in edges)}, next interval budget up to 45s')
    paths=sorted((n2/'family_pp').glob('q*/vertex_*.json'))+sorted((n2/'cert_split').glob('check_*/vertex_*.json'))
    candidates=[]
    for file in paths:
        m=physical_metrics(read(file));candidates.append((file,m))
    points=[]
    for a,b in targets:
        file,_=next((p,m) for p,m in candidates if max(abs(a-m['cmax']),abs(b-m['secondary']))<TOL)
        metrics,d=lift(cfg,read(file))
        assert abs(a-metrics['cmax'])<TOL and abs(b-metrics['secondary'])<TOL and metrics['rhythm']==0.
        points.append(dict(A=a,B=b,metrics=metrics,original_model_check=True,physical_checks=d['validation']['checks'],
                           source=file.resolve().relative_to(ROOT).as_posix(),sha256=digest(file)))
    assert len(points)==7 and len(edges)==17
    assert all(p['B']>q['B'] and p['A']<q['A'] for p,q in zip(points,points[1:]))
    qa=dict(physical_points=points,checks=edges,all_highs_or_temporal_exclusions=all(e['excluded'] for e in edges),
            original_config=meta['config'],tolerance=TOL,versions={n:version(n) for n in ('pyscipopt','scipy','numpy')},
            script_hashes={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},backend_hashes=meta['backend_hashes'])
    save(out/'validation.json',qa);log(out,f'7/7 original MILP and independent physical replays passed; alternate solver exclusion={qa["all_highs_or_temporal_exclusions"]}')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    try:verify(a.base,a.out)
    except BaseException:log(a.out,traceback.format_exc());raise

