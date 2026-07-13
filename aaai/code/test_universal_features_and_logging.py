"""Focused regression tests for the AAAI-27 feature schema and compact logs."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

AAAI_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = AAAI_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from global_const import (  # noqa: E402
    STRUCTURE_AWARE_CUT_FEATURE_SCHEMA,
    validate_checkpoint_feature_schema,
)
from logger import Logger  # noqa: E402
from utils import _build_structure_feature_tail, _extract_structure_profile  # noqa: E402


class _FakeVar:
    def __init__(self, var_type, obj=0.0, lb=0.0, ub=1.0):
        self._var_type = var_type
        self._obj = obj
        self._lb = lb
        self._ub = ub

    def vtype(self):
        return self._var_type

    def getObj(self):
        return self._obj

    def getLbGlobal(self):
        return self._lb

    def getUbGlobal(self):
        return self._ub


class _FakeCol:
    def __init__(self, var):
        self._var = var

    def getVar(self):
        return self._var

    def isIntegral(self):
        return False


class _FakeCut:
    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals

    def getCols(self):
        return self._cols

    def getVals(self):
        return self._vals


class UniversalFeatureTests(unittest.TestCase):
    def test_role_features_do_not_use_variable_names(self):
        cols = [
            _FakeCol(_FakeVar("BINARY")),
            _FakeCol(_FakeVar("INTEGER", ub=10)),
            _FakeCol(_FakeVar("CONTINUOUS", obj=1.0, ub=100)),
            _FakeCol(_FakeVar("CONTINUOUS", obj=0.0, ub=1e20)),
            _FakeCol(_FakeVar("OTHER", lb=-1e20, ub=1e20)),
        ]
        profile = _extract_structure_profile(_FakeCut(cols, [2, -3, 4, -1, 2]))

        self.assertEqual(profile["dominant_family"], "continuous_objective")
        self.assertAlmostEqual(profile["family_fractions"][0], 2 / 12)
        self.assertAlmostEqual(profile["family_fractions"][1], 3 / 12)
        self.assertAlmostEqual(profile["family_fractions"][2], 4 / 12)
        self.assertAlmostEqual(profile["family_fractions"][3], 1 / 12)
        self.assertAlmostEqual(profile["family_fractions"][4], 2 / 12)
        self.assertAlmostEqual(profile["bounded_ratio"], 9 / 12)
        self.assertAlmostEqual(profile["positive_ratio"], 8 / 12)
        self.assertAlmostEqual(profile["discrete_continuous_coupling"], 100 / 144)
        self.assertEqual(len(_build_structure_feature_tail(profile)), 10)

    def test_legacy_23d_checkpoint_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "retrain"):
            validate_checkpoint_feature_schema({}, 23, "legacy.pkl")
        validate_checkpoint_feature_schema(
            {"cut_feature_schema": STRUCTURE_AWARE_CUT_FEATURE_SCHEMA},
            23,
            "new.pkl",
        )
        # Legacy 13D HEM models remain loadable because their semantics did not change.
        validate_checkpoint_feature_schema({}, 13, "hem.pkl")


class CompactLoggerTests(unittest.TestCase):
    def test_filter_and_rotation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "debug.log"
            log = Logger()
            log.configure_text_logging(compact=True, max_mb=0.001, backup_count=1)
            log.add_text_output(str(path))
            with contextlib.redirect_stdout(io.StringIO()):
                log.log("large unneeded tensor dump " + "x" * 400)
                for index in range(3):
                    log.log("sampling worker {} ".format(index) + "x" * 550)
                log.log("forcedcuts length: 15")
                log.log("len cuts: 2317")
            log.remove_text_output(str(path))

            combined = path.read_text(encoding="utf-8")
            backup = Path(str(path) + ".1")
            if backup.exists():
                combined += backup.read_text(encoding="utf-8")
            self.assertNotIn("unneeded tensor", combined)
            self.assertIn("forcedcuts length: 15", combined)
            self.assertIn("len cuts: 2317", combined)
            self.assertTrue(backup.exists())


if __name__ == "__main__":
    unittest.main()
