import unittest,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'joint_model'))
from scip_imports import scip
from ortools.sat.python import cp_model
from integer_timing_export import export_model


class TranslationTests(unittest.TestCase):
    def fixture(self):
        m=scip.Model();m.hideOutput();s=m.addVar(name='start',ub=100);e=m.addVar(name='end',ub=100)
        maximum=m.addVar(name='max_wait',ub=100);cmax=m.addVar(name='Cmax',ub=100)
        m.addCons(e==s+3);m.addCons(cmax>=e)
        x=SimpleNamespace(model=m,cfg=SimpleNamespace(horizon=100),waits=[],rhythm=[],max_wait=maximum,cmax=cmax)
        return x,s,e

    def test_exact_difference_model(self):
        x,s,e=self.fixture();cp,vm,audit=export_model(x,{})
        solver=cp_model.CpSolver();status=solver.solve(cp)
        self.assertEqual(status,cp_model.OPTIMAL);self.assertEqual(solver.value(vm['Cmax']),3)
        self.assertEqual(audit['constraints'],x.model.getNConss())

    def test_reject_fractional_physical_constant(self):
        x,s,e=self.fixture();x.model.addCons(s>=0.5)
        with self.assertRaises(ValueError):export_model(x,{})

    def test_reject_nondifference_physical_constraint(self):
        x,s,e=self.fixture();x.model.addCons(s+e>=7)
        with self.assertRaises(ValueError):export_model(x,{})

    def test_reject_unrecognized_helper_constraint(self):
        x,s,e=self.fixture();x.model.addCons(s+e+x.max_wait>=7)
        with self.assertRaises(ValueError):export_model(x,{})

    def test_wait_with_constant_duration(self):
        x,s,e=self.fixture();w=x.model.addVar(name='wait_test',ub=100);x.waits=[w]
        x.model.addCons(w==e-s-3);x.model.addCons(x.max_wait>=w)
        cp,vm,audit=export_model(x,{})
        solver=cp_model.CpSolver();self.assertEqual(solver.solve(cp),cp_model.OPTIMAL)
        self.assertEqual(solver.value(vm['wait_test']),0)


if __name__=='__main__':unittest.main()
