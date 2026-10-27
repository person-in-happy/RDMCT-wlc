"""Exact incumbent-sublevel search; default main solve has no time limit.

Candidate capacity is justified by incumbent_sublevel.py, never a heuristic
restriction. A completed optimal solve still requires final original-model
verification before paper certification. Existing campaigns are not modified.
"""
from pathlib import Path
from dataclasses import replace,asdict
import argparse
import json
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'JMS-version/joint_model'))
from model import Config,Integrated
from seed import constrain_seed
from validate import validate,TOL
from run_experiments import dump,digest,assets,finite
from scip_imports import scip
from incumbent_sublevel import capacity_certificate,strengthen


class Checkpoint(scip.Eventhdlr):
    def __init__(self,x,out,cfg):
        self.x=x;self.out=out;self.cfg=cfg;self.last=0
    def eventinit(self):
        self.model.catchEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND,self)
        self.model.catchEvent(scip.SCIP_EVENTTYPE.LPSOLVED,self)
    def eventexit(self):
        self.model.dropEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND,self)
        self.model.dropEvent(scip.SCIP_EVENTTYPE.LPSOLVED,self)
    def eventexec(self,event):
        now=time.monotonic()
        newbest=event.getType()==scip.SCIP_EVENTTYPE.BESTSOLFOUND
        if now-self.last<15 and not newbest:return
        self.last=now;m=self.model
        dump(self.out/'progress.json',finite(dict(nodes=m.getNNodes(),seconds=m.getSolvingTime(),
             upper=m.getPrimalbound(),lower=m.getDualbound(),solutions=m.getNSols(),
             status=str(m.getStatus()),eta='unknown; proof completion is data dependent')))
        if newbest and m.getNSols():
            sol=m.getBestSol();data=self.x.result(sol);data['config']=asdict(self.cfg)
            data['validation']=validate(data)
            data.update(experiment_scope='exact_incumbent_sublevel',full_candidate_space=False,
                        global_optimality_claim=False,primary_status='in_progress')
            if data['validation']['valid']:
                dump(self.out/'checkpoint.json',finite(data))
                dump(self.out/'checkpoint_variables.json',dict(values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}))


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--certificate',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--probe-seconds',type=float,default=0,help='Explicit diagnostic only; 0 means no main time limit')
    parser.add_argument('--memory-mb',type=float,default=6000)
    args=parser.parse_args()
    if args.probe_seconds<0 or args.memory_mb<=0:parser.error('Invalid resource limit')
    source=Path(args.source).resolve();certpath=Path(args.certificate).resolve();out=Path(args.output).resolve()
    data=json.loads(source.read_text(encoding='utf-8-sig'));cert=json.loads(certpath.read_text(encoding='utf-8-sig'))
    if not cert['accepted'] or not cert['full_candidate_space'] or cert['source_sha256']!=digest(source) or cert['assets']!=assets():
        raise ValueError('Matching current ORIGINAL-model feasibility certificate required')
    replay=validate(data)
    if not replay['valid']:raise ValueError(replay['errors'])
    cfg=Config(**data['config']);upper=replay['product_return_cmax']
    proof=capacity_certificate(cfg,upper)
    compact=replace(cfg,max_pairs=proof['pairs'],max_cycles=proof['cycles_per_chamber'])
    out.mkdir(parents=True,exist_ok=False)
    manifest=dict(source=str(source),source_sha256=digest(source),original_certificate=str(certpath),
                  original_certificate_sha256=digest(certpath),assets=assets(),config=asdict(cfg),
                  script_sha256=digest(Path(__file__)),bound_code_sha256=digest(Path(__file__).with_name('incumbent_sublevel.py')),
                  capacity_certificate=proof,probe_seconds=args.probe_seconds,memory_mb=args.memory_mb,
                  threads=1,main_time_limit=None if not args.probe_seconds else args.probe_seconds,
                  scope='Exact original-objective sublevel; final original-model verification pending')
    dump(out/'manifest.json',manifest)
    print('BUILD EXACT SUBLEVEL '+json.dumps(proof),flush=True)
    x=Integrated(compact);m=x.model;m.hideOutput(False)
    m.setIntParam('parallel/maxnthreads',1);m.setIntParam('randomization/randomseedshift',1)
    m.setRealParam('limits/memory',args.memory_mb);m.setLogfile(str(out/'solver.log'))
    cuts=strengthen(x,upper,proof);dump(out/'strengthening.json',cuts)
    fix=constrain_seed(x,data);m.setObjective(0,'minimize');m.setRealParam('limits/time',120)
    m.optimize()
    if not m.getNSols():raise RuntimeError('Certified incumbent failed sublevel completion')
    sol=m.getBestSol();values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
    m.freeTransform()
    for v,lb,ub in fix:m.chgVarLb(v,lb);m.chgVarUb(v,ub)
    m.setObjective(x.cmax,'minimize')
    sol=m.createSol()
    for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
    if not m.checkSol(sol,printreason=False,completely=True):raise RuntimeError('Strengthening excluded certified incumbent')
    m.addSol(sol)
    # Root separation budget controls work allocation, not the feasible set.
    m.setIntParam('separating/maxroundsroot',5)
    m.setRealParam('limits/time',args.probe_seconds if args.probe_seconds else 1e20)
    checkpoint=Checkpoint(x,out,cfg)
    m.includeEventhdlr(checkpoint,'sublevel_checkpoint','Save feasible incumbents and live bounds')
    dump(out/'build.json',dict(variables=m.getNVars(),constraints=m.getNConss(),safe_sublevel=proof))
    print('SEARCH all pairings/chambers/cleaning choices within proven incumbent sublevel; ETA unknown',flush=True)
    m.optimize()
    result=x.result();result['config']=asdict(cfg);result['validation']=validate(result)
    model_check=bool(m.getNSols() and m.checkSol(m.getBestSol(),printreason=False,completely=True))
    result.update(experiment_scope='exact_incumbent_sublevel',full_candidate_space=False,
                  original_model_check=False,sublevel_model_check=model_check,
                  primary_status=str(m.getStatus()),primary_bound=m.getDualbound(),
                  primary_gap=m.getGap(),capacity_certificate=proof,global_optimality_claim=False,
                  pending='Verify final incumbent in original full-capacity model, then combine with capacity theorem')
    dump(out/'result.json',finite(result))
    if m.getNSols():
        sol=m.getBestSol();dump(out/'variables.json',dict(values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}))
    dump(out/'finished.json',dict(status=str(m.getStatus()),physical_valid=result['validation']['valid'],
          sublevel_model_check=model_check,sublevel_optimal=str(m.getStatus())=='optimal',paper_certified=False))
    print('SUBLEVEL FINISHED '+json.dumps(finite(dict(status=str(m.getStatus()),upper=result.get('cmax'),lower=result.get('primary_bound')))),flush=True)
    m.freeProb()

if __name__=='__main__':main()
