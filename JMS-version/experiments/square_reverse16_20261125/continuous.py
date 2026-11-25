"""Prove one continuous 16-wafer family using common integer decisions in the original model."""
from pathlib import Path
from collections import Counter
from fractions import Fraction
import hashlib, json, math, msvcrt, os, sys, time
HERE=Path(__file__).resolve().parent;JMS=HERE.parents[1];EX=HERE.parent
sys.path.insert(0,str(EX/'square_residence_20261125'))
from solver import cell,read,save,sha
from score import metrics
sys.path.insert(0,str(cell.BACKENDS['D']))
from model import Config,Integrated
from validate import validate
OUT=JMS/'results/square_reverse16_20261125'
F=OUT/'continuous'
def emit(path,d):
    tmp=path.with_suffix(f'.{os.getpid()}.tmp');tmp.write_text(json.dumps(d,indent=2),encoding='utf8');os.replace(tmp,path)
def main():
    F.mkdir(parents=True,exist_ok=True);lk=(F/'run.lock').open('a+b')
    try:msvcrt.locking(lk.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    source=OUT/'last_tight_d16/native';s0=read(source/'schedule.json');a0=cell.values(source/'assignment.json.gz')
    ident=dict(source=sha(source/'assignment.json.gz'),script=sha(Path(__file__)),native=sha(cell.BACKENDS['D']/'model.py'))
    out=F/'proof.json'
    if out.exists():
        assert read(out)['identity']==ident;return
    start=time.monotonic()
    def status(k,stage):
        dt=time.monotonic()-start;left=50*(4-k)/4 if k==0 else dt*(4-k)/k
        emit(F/'progress.json',dict(identity=ident,completed=k,total=4,failed=0,stage=stage,elapsed_s=dt,estimated_total_s=dt+left,remaining_s=left,basis='four original-model stages; historical initial 50s; observed stage mean thereafter'))
        print(stage,k,'/4 elapsed',round(dt,1),'ETA',round(left,1),flush=True)
    status(0,'Load complete native assignments and linear rows')
    x=Integrated(Config(**s0['config']));m=x.model;cell.scip_settings(m,dict(n=16,seed=1,seconds=30,gap=0),F)
    m.setRealParam('numerics/feastol',1e-9)
    vs=list(m.getVars(transformed=False));org=m.getNConss();assert org==1109436
    rowtypes=Counter(c.getConshdlrName() for c in m.getConss(transformed=False));assert set(rowtypes)=={'linear'},rowtypes
    iv=[v for v in vs if v.vtype()!='CONTINUOUS']
    integer_digest=hashlib.sha256()
    for v in sorted(iv,key=lambda v:v.name):
        z=round(a0.get(v.name,0));assert abs(a0.get(v.name,0)-z)<1e-7
        integer_digest.update(f'{v.name}={z}\n'.encode());m.chgVarLb(v,z);m.chgVarUb(v,z)
    active=[j for j in s0['jobs'] if j['product']]
    group={w['name']:('zero' if w['pjob']=='Pjob1' else 'last' if w['unload_start']-w['load_end']>186.5 else 'moving') for w in active}
    assert Counter(group.values())=={'zero':8,'moving':7,'last':1}
    final=next(w['name'] for w in active if w['loan_end']==986.)
    endpoint=F/'endpoint';endpoint.mkdir(exist_ok=True)
    checksum=endpoint/'verification.json'
    if not checksum.exists():
        temp=[m.addCons(x.cmax==987.125),m.addCons(x.jobs[final]['last']['e']==987.125)]
        for name,role in group.items():
            target={'zero':0.,'last':7.,'moving':6.5625}[role];j=x.jobs[name]
            temp.append(m.addCons(j['unload_s']-j['load_e']==180.+target))
        m.setObjective(x.cmax,'minimize');m.optimize();sol=m.getBestSol()
        assert sol is not None,str(m.getStatus());assert m.checkSol(sol,original=True,completely=True)
        s1=x.result(solution=sol);a1={v.name:m.getSolVal(sol,v) for v in vs}
        assert validate(s1)['valid']
        assert max(abs(a1.get(v.name,0)-a0.get(v.name,0)) for v in iv)<1e-8
        assert abs(metrics(s1)['secondary']-3.404296875)<1e-8
        save(endpoint/'schedule.json',s1);save(endpoint/'assignment.json.gz',cell.sparse(a1))
        emit(checksum,dict(identity=ident,files={f:sha(endpoint/f) for f in ['schedule.json','assignment.json.gz']}))
        m.freeTransform()
        for c in temp:m.delCons(c)
    else:
        rec=read(checksum);assert rec['identity']==ident
        assert all(sha(endpoint/f)==h for f,h in rec['files'].items())
    a1=cell.values(endpoint/'assignment.json.gz')
    assert all(abs(a0.get(v.name,0)-a1.get(v.name,0))<1e-8 for v in iv)
    status(1,'Common full integer skeleton and exact terminal endpoint')
    samples=[]
    for slope in (Fraction(0),Fraction(1,13),Fraction(1,4),Fraction(1,2),Fraction(7,11),Fraction(7,8),Fraction(1)):
        t=float(slope);values={k:(1-t)*a0.get(k,0)+t*a1.get(k,0) for k in (a0.keys()|a1.keys())}
        sol=cell.attach(x,values);doc=x.result(solution=sol);m.freeSol(sol)
        f=metrics(doc);r=validate(doc);D=1-9/16*t;mean=3.5-7/16*D;C=988-2*D
        assert r['valid'] and f['clean_deficit']==0
        assert max(abs(f[key]-expected) for key,expected in [('cmax',C),('mean_residence',mean),('residence_range',D),('secondary',mean+D*D/2)])<1e-8
        samples.append(dict(t=str(slope),C=C,D=D,mean=mean,fB=f['secondary'],all_original_rows_verified=org,physical_replay_checks=r['checks']))
    status(2,'Interior convex combinations and event replay')
    z=m.addVar(name='family_spread',lb=0.,ub=100.)
    for j in active:
        wa=x.jobs[j['name']];v=wa['unload_s']-wa['load_e']
        for k in active:
            if k['pjob']==j['pjob'] and j['name']!=k['name']:
                wc=x.jobs[k['name']];m.addCons(z>=v-(wc['unload_s']-wc['load_e']))
    m.setObjective(x.cmax+2*z,'minimize');m.optimize()
    assert str(m.getStatus())=='optimal'
    bound=float(m.getDualbound());upper=float(m.getObjVal());assert bound>987.99999 and upper<988.00001
    status(3,'Native fixed-skeleton support lower bound C+2D')
    y=3.4921875;cross=987.125-math.sqrt(8*(y-3.404296875))
    emit(out,dict(identity=ident,config=s0['config'],native_rows=org,row_handlers=dict(rowtypes),native_vars=len(vs),
        common_integer_vars=len(iv),max_integer_difference=max(abs(a0.get(v.name,0)-a1.get(v.name,0)) for v in iv),
        integer_sha256=integer_digest.hexdigest(),endpoints=[dict(t=0,schedule=(source/'schedule.json').relative_to(JMS).as_posix(),assignment=(source/'assignment.json.gz').relative_to(JMS).as_posix(),assignment_sha256=sha(source/'assignment.json.gz')),
        dict(t=1,schedule=(endpoint/'schedule.json').relative_to(JMS).as_posix(),assignment=(endpoint/'assignment.json.gz').relative_to(JMS).as_posix(),assignment_sha256=sha(endpoint/'assignment.json.gz'))],
        family=dict(C='986+9t/8',D='1-9t/16',mean='7/2-7D/16',E=0,fB='3.404296875+(987.125-C)^2/8',t_interval=[0,1],C_interval=[986,987.125],
            common_last_wafer=next(w['identity'] for w in active if w['name']==final),
            roles={k:[w['identity'] for w in active if group[w['name']]==k] for k in ['zero','moving','last']}),
        support=dict(scope='fixed complete original integer assignment',min_C_plus_2D_lower=bound,upper=upper,status=str(m.getStatus()),physical_mean_lower='mean >= 7/2 - 7D/16',global_frontier_coverage='not certified'),
        comparison=dict(reference_C=979,reference_fB=3.4921875,open_at= cross,closed_at=987.125,scope='relative to reference; compare additional archived schedules independently'),samples=samples))
    m.freeProb();status(4,'Native continuous family verified')
if __name__=='__main__':main()
