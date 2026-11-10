"""Regression for original dimensions; mock solver only, no experiments."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import unittest
import time

DRIVER = Path(__file__).resolve().parents[1] / 'JMS-version/tools/default_gap_experiments.py'

class EncodingDimensionsTest(unittest.TestCase):
    def exercise(self, check_only):
        model = MagicMock()
        transformed = False
        def optimize():
            nonlocal transformed
            transformed = True
        model.optimize.side_effect = optimize
        model.getStatus.return_value = 'optimal'
        model.getDualbound.return_value = 1
        model.getSolvingTime.return_value = 0.1
        x = SimpleNamespace(model=model, bounded=False, result=lambda **kw: {'original_model_check': True})
        dims = {'variables': 3, 'constraints': 2, 'linear_nonzeros': 4}
        def dimensions(obj):
            if transformed:
                raise Warning('coefficients not available for constraints of type setppc')
            return dims.copy()
        dimensions_mock = MagicMock(side_effect=dimensions)
        strengthening = MagicMock(spec=['lift_start', 'assignment_solution', 'assert_wafer_decode', 'audit_full'])
        strengthening.audit_full.return_value = {'valid': True}
        followup = SimpleNamespace(build_fair=lambda *a: x, dimensions=dimensions_mock,
            finite_bound=lambda v: v, save_assignment=lambda *a: {})
        namespace = dict(read=lambda p: {'config': {}, 'values': {}},
            backend=SimpleNamespace(Config=lambda **kw: kw), followup=followup,
            strengthening=strengthening, time=time, validate=lambda d: {'valid': True},
            fix_structure=MagicMock(), BACKEND='mock', incumbent_checks=lambda m: {},
            dump=MagicMock(), finite=lambda d: d, review=SimpleNamespace(physical_metrics=lambda d: {}),
            digest=lambda p: 'mock', Path=Path)
        tree = ast.parse(DRIVER.read_text(encoding='utf-8-sig'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'encoding_run')
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(DRIVER), 'exec'), namespace)
        result = namespace['encoding_run']({'source':'source', 'values':'values', 'arm':'pjob', 'seed':1},
            Path('unused'), {'time_limit':1, 'memory_mb':100}, check_only=check_only)
        self.assertEqual(result['dimensions'], dims)
        dimensions_mock.assert_called_once_with(x)
        model.freeProb.assert_called_once()
        if check_only:
            model.optimize.assert_not_called()
            namespace['dump'].assert_not_called()
        else:
            model.optimize.assert_called_once()
            strengthening.audit_full.assert_called_once()
    def test_solved_model_uses_original_dimensions(self):
        self.exercise(False)
    def test_check_only_does_not_optimize(self):
        self.exercise(True)

if __name__ == '__main__':
    unittest.main()