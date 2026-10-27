"""Feasibility acceptance must use the original stage model and retain diagnostics."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_experiments import incumbent_checks
from pyscipopt import Model


class CandidateModel:
    def __init__(self,model,solution):self.model=model;self.solution=solution
    def getNSols(self):return 1
    def getBestSol(self):return self.solution
    def checkSol(self,*a,**kw):return self.model.checkSol(*a,**kw)


def test_original_constraint_violation_is_still_rejected():
    m=Model();m.hideOutput()
    try:
        x=m.addVar('x',vtype='B');y=m.addVar('y',lb=0,ub=3)
        m.addCons(y>=2*x)
        good=m.createSol();m.setSolVal(good,x,1);m.setSolVal(good,y,2)
        bad=m.createSol();m.setSolVal(bad,x,1);m.setSolVal(bad,y,0)
        assert incumbent_checks(CandidateModel(m,good))['original_model_check']
        assert not incumbent_checks(CandidateModel(m,bad))['original_model_check']
        m.freeSol(good);m.freeSol(bad)
    finally:m.freeProb()


def test_confirmed_transformed_domain_mismatch_is_not_acceptance_failure():
    # Simulate the exact two-check outcome captured by the live 4-wafer replay.
    # A trivial one-variable presolve need not leave the same search-node bounds.
    class FinalNodeBounds(CandidateModel):
        def checkSol(self,*a,**kw):
            if not kw.get('original',False):return False
            return super().checkSol(*a,**kw)
    m=Model();m.hideOutput()
    try:
        x=m.addVar('x',vtype='B');m.setObjective(x,'minimize')
        candidate=m.createOrigSol();m.setSolVal(candidate,x,1)
        m.optimize()
        result=incumbent_checks(FinalNodeBounds(m,candidate))
        assert result['original_model_check']
        assert not result['transformed_model_check']
        m.freeSol(candidate)
    finally:m.freeProb()


def test_no_incumbent_does_not_pass():
    m=Model();m.hideOutput()
    try:
        m.addVar('x')
        assert incumbent_checks(m)['original_model_check'] is False
    finally:m.freeProb()
