"""Regression tests for SPBS completion and five-cell continuation without warm starts."""
import json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import vtr_sensitivity as runner
from model import Config
from seed import construct

def save(dest,cfg):
    dest.mkdir(parents=True)
    data=construct(cfg)
    (dest/'result.json').write_text(json.dumps(data),encoding='utf-8')
    return data

def small():
    return Config({'LP1':{'4x1':1},'LP2':{},'LP3':{},'LP4':{}})

def test_completed_spbs_does_not_require_common_warm_start(tmp_path):
    save(tmp_path/'cell',small())
    assert runner.completed(tmp_path/'cell')
    assert not (tmp_path/'cell/warm_start_check.json').exists()

@pytest.mark.parametrize('fault',['wrong_hand','legacy'])
def test_invalid_saved_result_is_not_skipped(tmp_path,fault):
    data=save(tmp_path/'cell',small())
    if fault=='wrong_hand':next(j for j in data['jobs'] if j['product'])['vtr_hand_in']='C1'
    else:data['config']['vtr_hand_policy']='legacy_unrestricted'
    (tmp_path/'cell/result.json').write_text(json.dumps(data))
    with pytest.raises(RuntimeError):runner.completed(tmp_path/'cell')

def test_partial_result_is_incomplete(tmp_path):
    assert not runner.completed(tmp_path)
    (tmp_path/'result.json').write_text('{')
    assert not runner.completed(tmp_path)

def test_resume_keeps_first_cell_and_executes_only_four_missing(tmp_path,monkeypatch):
    output=tmp_path/'campaign';output.mkdir()
    first=output/'process_090'
    save(first,Config(runner.ports(8,'mixed'),full_time=162,mix_time=81))
    original=(first/'result.json').read_bytes();calls=[]
    monkeypatch.setattr(runner,'assets',lambda:{})
    def fake_solve(config,dest,**kwargs):
        calls.append(dest.name);save(dest,Config(**json.loads(config.read_text())))
    monkeypatch.setattr(runner,'solve',fake_solve)
    runner.run(output)
    assert calls==['process_110','dummy_04','dummy_06','dummy_10']
    assert (first/'result.json').read_bytes()==original
    calls.clear();runner.run(output);assert calls==[]
