"""Unrestricted original SCIP model and frozen RL-DMCT cut policy with isolated outputs."""
import time
from common import TOL, lower_bound, metrics
from model import Integrated
from scip_imports import scip
from validate import validate
from witness import sparse_witness


class Native:
    def __init__(self,cfg,seed,weight,learned=False):
        self.x = Integrated(cfg)
        self.m = m = self.x.model
        self.variables = m.getVars(transformed=False)
        self.weight = weight
        self.B = scip.quicksum(self.x.waits)+10*self.x.max_wait+weight*scip.quicksum(self.x.rhythm)
        self.PP = scip.quicksum(self.x.pair.product[p,1] for p in range(self.x.N))
        m.setIntParam("parallel/maxnthreads",1)
        m.setIntParam("lp/threads",1)
        m.setIntParam("randomization/randomseedshift",seed)
        m.setRealParam("limits/memory",2400)
        m.setRealParam("numerics/feastol",1e-7)
        self.agent,self.policy = None,None
        if learned:
            import torch
            torch.set_num_threads(1)
            from joint_algorithms import install
            self.agent,self.policy = install(m,"proposed",1)

    def warm(self,data,add=False):
        vals = sparse_witness(self.x.cfg,data)
        sol = self.m.createSol()
        for v in self.variables:
            if v.name in vals:
                self.m.setSolVal(sol,v,float(vals[v.name]))
        valid = self.m.checkSol(sol,printreason=False,completely=True,original=True)
        if valid:
            event_metrics = metrics(data,self.weight)
            valid = (abs(self.m.getSolVal(sol,self.x.cmax)-event_metrics["cmax"])<=TOL
                     and abs(self.m.getSolVal(sol,self.B)-event_metrics["secondary"])<=TOL)
        if add and valid:
            self.m.addSol(sol)
        else:
            self.m.freeSol(sol)
        return bool(valid)

    def query(self,goal,cap,screen,parents,deadline):
        m,x = self.m,self.x
        m.freeTransform()
        temporary = []
        log = {"goal":goal,"cap":cap,"scope":"unrestricted","nodes":0,"warm":0}
        try:
            if cap is not None:
                temporary.append(m.addCons(self.B<=cap+1e-7))
                if screen:
                    allowed = [p for p in range(x.N//2+1) if lower_bound(x.cfg,x.N,p)<=cap+TOL]
                    if not allowed:
                        return [], log | {"status":"infeasible_by_pair_bound"}
                    temporary.append(m.addCons(self.PP<=max(allowed)))
            for record in parents:
                if time.monotonic()+.02>=deadline:
                    break
                if cap is None or record["b"]<=cap+TOL:
                    log["warm"] += self.warm(record["data"], True)
            solutions = []
            for pass_no,key in enumerate((goal,"B" if goal=="A" else "A")):
                left = deadline-time.monotonic()
                if left < .015:
                    log.setdefault("status","deadline_before_solve")
                    break
                m.setObjective(x.cmax if key=="A" else self.B,"minimize")
                m.setRealParam("limits/time",max(.005,left*.95))
                m.optimize()
                status = str(m.getStatus())
                log["nodes"] += int(m.getNNodes())
                if not pass_no:
                    log.update(status=status,dual_bound=float(m.getDualbound()))
                sol = m.getBestSol()
                if sol is None:
                    break
                if not m.checkSol(sol,printreason=False,completely=True,original=True):
                    log["status"] = "candidate_rejected_original_rows"
                    break
                data = x.result(solution=sol)
                result = validate(data)
                if not result["valid"]:
                    raise ValueError(str(result["errors"][:4]))
                data["validation"] = result
                ms = metrics(data,self.weight)
                if cap is not None and ms["secondary"]>cap+TOL:
                    raise ValueError("SCIP violated the physical cap")
                solutions.append(data)
                if pass_no or status != "optimal":
                    break
                optimum = m.getSolObjVal(sol)
                m.freeTransform()
                temporary.append(m.addCons((x.cmax if key=="A" else self.B)<=optimum+1e-7))
            return solutions,log
        finally:
            m.freeTransform()
            for c in reversed(temporary):
                m.delCons(c)

    def close(self):
        self.m.freeProb()
