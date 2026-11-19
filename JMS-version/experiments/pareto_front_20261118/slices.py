"""Continuous Pareto slices of archived feasible assignments on the original D model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
import numpy as np
from scipy import sparse
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parents[3]
JMS = ROOT / 'JMS-version'
BACKEND = JMS / 'model4_pjob_nonprocessing_20261103'
sys.path[:0] = [str(BACKEND), str(ROOT), str(JMS / 'experiments/finite_budget_20261116')]
from model import Config, Integrated
from validate import validate
from finite_budget import physical_metrics

CASES = {
    'n2': ('n2_2x2_scenario1', 's1_ablation_20261117_r1', 'rows.json'),
    'n4': ('n4_H10_mixed_dual', 'journal_d_algorithm_t1_20261108_unlimited_r1', 'cells.json'),
}
TOL = 2e-5

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
    tmp.replace(path)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def log(out, message):
    print(message, flush=True)
    with (out/'progress.log').open('a', encoding='utf-8') as f:
        print(message, file=f)

def inventory(case):
    key, batch, summary = CASES[case]
    base = JMS/'results'/batch
    rows = [r for r in read(base/'summary'/summary) if r['case']==key]
    assert {r['id'] for r in rows} == {r['id'] for r in read(base/'campaign.json')['cells'] if r['case']==key}
    assert all(r['valid'] and r.get('budget_eligible',True) for r in rows)
    return [base/'runs'/r['id'] for r in rows]

class Projected:
    def __init__(self, model):
        self.x = model
        self.m = m = model.model
        self.variables = variables = m.getVars(transformed=False)
        self.names = [v.name for v in variables]
        self.ic = np.array([i for i,v in enumerate(variables) if v.vtype()=='CONTINUOUS'])
        self.id = np.array([i for i,v in enumerate(variables) if v.vtype()!='CONTINUOUS'])
        index = {name:i for i,name in enumerate(self.names)}
        assert len(index)==len(variables)
        self.bounds = [(variables[i].getLbOriginal(), variables[i].getUbOriginal()) for i in self.ic]
        self.ca = np.asarray([int(variables[i].name==model.cmax.name) for i in self.ic], dtype=float)
        m.setObjective(model.secondary_objective, 'minimize')
        obj = np.asarray([v.getObj() for v in variables])
        self.cb, self.discrete_obj = obj[self.ic], obj[self.id]
        self.offset = m.getObjoffset()
        rr, cc, vv, lhs, rhs = [], [], [], [], []
        for i, cons in enumerate(m.getConss(transformed=False)):
            assert cons.getConshdlrName()=='linear'
            for key,value in m.getValsLinear(cons).items():
                rr.append(i); cc.append(index[key]); vv.append(value)
            lhs.append(m.getLhs(cons)); rhs.append(m.getRhs(cons))
        matrix = sparse.csr_matrix((vv,(rr,cc)), shape=(len(lhs),len(variables)))
        self.cm, self.dm = matrix[:,self.ic], matrix[:,self.id]
        self.lo, self.hi = np.asarray(lhs), np.asarray(rhs)
        self.has_cont = np.diff(self.cm.indptr)>0
        self.eq = self.has_cont & (self.lo==self.hi)
        self.upper = self.has_cont & (self.hi< m.infinity()/2) & ~self.eq
        self.lower = self.has_cont & (self.lo> -m.infinity()/2) & ~self.eq
        self.aeq = self.cm[self.eq]
        self.aub = sparse.vstack((self.cm[self.upper],-self.cm[self.lower]),format='csr')
        self.lps = 0

    def setup(self, discrete):
        self.discrete = discrete
        integer_lhs = self.dm @ discrete
        pure = ~self.has_cont
        assert np.all(self.lo[pure]-TOL <= integer_lhs[pure]) and np.all(integer_lhs[pure] <= self.hi[pure]+TOL)
        self.beq = (self.lo-integer_lhs)[self.eq]
        self.bub = np.r_[(self.hi-integer_lhs)[self.upper], (integer_lhs-self.lo)[self.lower]]
        self.constant = float(self.offset + self.discrete_obj @ discrete)

    def solve(self, obj, same=None):
        ae, be = self.aeq, self.beq
        if same is not None:
            ae = sparse.vstack((ae, sparse.csr_matrix(same[0][None,:])), format='csr')
            be = np.r_[be,same[1]]
        self.lps += 1
        result = linprog(obj, A_ub=self.aub,b_ub=self.bub,A_eq=ae,b_eq=be,
                         bounds=self.bounds, method='highs', options={'primal_feasibility_tolerance':1e-8,'dual_feasibility_tolerance':1e-8})
        if not result.success:
            raise ValueError(result.message)
        return result.x

    def verify(self, continuous):
        vals = np.empty(len(self.variables))
        vals[self.ic], vals[self.id] = continuous, self.discrete
        sol = self.m.createSol()
        for v,value in zip(self.variables,vals): self.m.setSolVal(sol,v,float(value))
        try:
            if not self.m.checkSol(sol,printreason=True,completely=True,original=True):
                raise ValueError('Rejected by unrestricted original model')
            d = self.x.result(solution=sol)
            check = validate(d)
            if not check['valid']: raise ValueError(check['errors'])
            stats = physical_metrics(d)
            pair = np.array([stats['cmax'],stats['secondary']])
            assert np.max(abs(pair-[self.ca@continuous, self.cb@continuous+self.constant])) < TOL, pair
            return pair
        finally:
            self.m.freeSol(sol)

    def front(self):
        a, b = self.ca, self.cb
        left = self.solve(b, (a, a@self.solve(a)))
        right = self.solve(a, (b, b@self.solve(b)))
        pts = []
        def xy(v): return np.array([a@v, b@v+self.constant])
        def split(v, w, depth=0):
            if depth>=150: raise ValueError('Dichotomic search did not converge')
            p,q = xy(v),xy(w)
            if np.max(abs(p-q)) <= TOL: return
            da,db = q[0]-p[0],p[1]-q[1]
            if min(da,db)<-TOL: raise ValueError((p,q))
            weight = np.array([db,da])/max(da,db)
            mid = self.solve(weight[0]*a+weight[1]*b)
            r = xy(mid)
            if weight@(p-r) <= 2e-7: return
            split(v,mid,depth+1); pts.append(mid); split(mid,w,depth+1)
        split(left,right)
        return [left,*pts,right] if max(abs(xy(left)-xy(right)))>TOL else [left]

def run(case,out):
    dirs=inventory(case)
    start=time.monotonic()
    log(out,f'{case}: building complete physical model; 0/{len(dirs)} records, failures=0')
    cfg=read(dirs[0]/'result.json')['config']
    x=Integrated(Config(**cfg))
    assert not x.bounded
    pg=Projected(x)
    summary=dict(case=case, config=cfg, backend_hashes={n.name:digest(n) for n in BACKEND.glob('*.py')},
                 script_sha256=digest(__file__), tolerance=TOL, variables=pg.names,
                 discrete_indices=pg.id.tolist(),continuous_indices=pg.ic.tolist(),slices=[])
    seen={}
    for i,d in enumerate(dirs,1):
        file=d/'variables.json'
        if read(d/'result.json')['config']!=cfg: raise ValueError('Case configurations differ')
        vals=read(file)['values']
        if set(vals)!=set(pg.names): raise ValueError('Variable names differ')
        disc=np.array([round(vals[pg.names[j]]) for j in pg.id], dtype=np.int32)
        ident=hashlib.sha256(disc.astype('<i4').tobytes()).hexdigest()
        if ident not in seen:
            pg.setup(disc)
            vertices=pg.front()
            pairs=[pg.verify(v).tolist() for v in vertices]
            ix=len(summary['slices'])
            seen[ident]=ix
            np.savez_compressed(out/f'slice_{ix:03}.npz',d=disc, v=np.array(vertices))
            summary['slices'].append(dict(integer_sha256=ident, source=str(file.relative_to(ROOT)), input_sha256=digest(file),
                                          vertices=pairs, records=[]))
        summary['slices'][seen[ident]]['records'].append(d.name)
        if i%5==0 or i==1 or i==len(dirs):
            elapsed=time.monotonic()-start
            log(out,f'{case}: completed={i}/{len(dirs)} failed=0 structures={len(seen)} LPs={pg.lps} elapsed={elapsed:.1f}s ETA={elapsed*(len(dirs)-i)/i:.1f}s')
    summary.update(records=len(dirs),lp_solves=pg.lps,elapsed=time.monotonic()-start)
    save(out/'slices.json',summary)
    x.model.freeProb()

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('case',choices=CASES);p.add_argument('directory',type=Path)
    args=p.parse_args()
    args.directory.mkdir(parents=True,exist_ok=False)
    try: run(args.case,args.directory)
    except BaseException:
        log(args.directory,traceback.format_exc())
        raise

