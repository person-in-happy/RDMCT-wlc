"""Run the unrelated timeout case with the pre-change cleaning implementation in memory."""
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'JMS-version/joint_model'),str(ROOT)]
import model
import joint_chamber_cycle_model as cycles
old=Path(cycles.__file__).read_text(encoding='utf-8-sig').replace(
    'model.addCons(prev>=k)',
    "model.addCons(prev>=(H-1)*k)\n            next_mix=kind[c,q+1,'2x2'] if q+1<cycle_limit else 0\n            model.addCons(prev+next_mix>=H*k)")
exec(compile(old,cycles.__file__,'exec'),cycles.__dict__)
old_model=Path(model.__file__).read_text(encoding='utf-8-sig').replace(
    'clean_bound=productive\n','clean_bound=productive//(cfg.cleaning_interval-1)\n')
exec(compile(old_model,model.__file__,'exec'),model.__dict__)
raise SystemExit(pytest.main([str(ROOT/'JMS-version/joint_model/test_integrated.py')+
    '::test_single_source_accompanied_entry_and_early_drop_rejected','-q']))
