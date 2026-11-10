"""Protocol tests only: no scientific optimization or training."""
from pathlib import Path
import importlib.util
import os
import json
import pytest
import time
from types import SimpleNamespace
from contextlib import nullcontext
import sys

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cie_current_protocol',ROOT/'cie/code/run_current_jms_experiments.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

def test_generalization_preserves_all_predefined_cases():
    rows=entry.case_plan('generalization')
    assert len(rows)==27
    assert len({json.dumps({k:v for k,v in r.items() if k!='case'},sort_keys=True) for r in rows})==27
    assert {r['n'] for r in rows}=={2,4,8}
    assert {r['dummy_count'] for r in rows}=={4,6,8}
    for r in rows:
        assert sum(sum(v.values()) for v in r['load_ports'].values())==r['n']

def test_campaign_cannot_target_old_results():
    with pytest.raises(ValueError):entry.safe_campaign(ROOT/'cie/results/main')
    with pytest.raises(ValueError):entry.safe_campaign(entry.BASE)
    assert entry.safe_campaign(entry.BASE/'fresh').parent==entry.BASE

def test_late_better_incumbent_is_not_budget_qualified(tmp_path):
    rows=[('checkpoint_00001.json',10,90,91,True),
          ('checkpoint_00002.json',5,99,101,True),
          ('checkpoint_00003.json',4,101,99,True),
          ('checkpoint_00004.json',3,99,99,False)]
    for name,cmax,checked,written,valid in rows:
        p=tmp_path/name;entry.dump(p,dict(cmax=cmax,validated_epoch=checked,valid=valid));os.utime(p,(written,written))
    selected=entry.checkpoint_files(tmp_path,100)
    assert len(selected)==1 and selected[0][0]==10

def test_no_incumbent_and_errors_stay_in_denominator(tmp_path):
    entry.dump(tmp_path/'campaign.json',dict(cells=[{'id':x} for x in ('a','b','c')]))
    entry.dump(tmp_path/'runs/a/execution.json',dict(execution_error=False,qualified_incumbent=None))
    entry.dump(tmp_path/'runs/b/execution.json',dict(execution_error=True,qualified_incumbent=None))
    assert entry.coverage(tmp_path)==dict(expected=3,complete=2,failed=1,pending=1,valid=0)

def test_main_has_no_fixed_memory_arguments():
    text=(ROOT/'cie/code/run_current_jms_experiments.py').read_text('utf-8')
    assert "setRealParam('limits/memory'" not in text
    assert "'--memory-mb'" not in text and "'--process-memory-mb'" not in text

def test_failed_construction_falls_back_and_keeps_failure_record(tmp_path,monkeypatch):
    import psutil
    c=dict(id='one',case='case',initialization='spbs',method='scip',seed=1,training_seed=1)
    s=dict(cells=[c],settings=dict(budget=5,init_fraction=.2,wall_grace=.1,min_available_fraction=.1))
    out=tmp_path/'campaign';out.mkdir();entry.dump(out/'campaign.json',s)
    monkeypatch.setattr(entry,'checked',lambda out:s)
    monkeypatch.setattr(entry,'BASE',tmp_path)
    monkeypatch.setattr(psutil,'process_iter',lambda *args:[])
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=90,total=100))
    monkeypatch.setitem(sys.modules,'run_matched_supplement',SimpleNamespace(output_lock=lambda _:nullcontext()))
    monkeypatch.setitem(sys.modules,'paper_defaults',SimpleNamespace(ensure_idle=lambda:None))
    calls=[]
    def fake_execute(out,cell,stage,deadline,grace,min_available,warm=None,progress=None):
        calls.append((stage,deadline,warm))
        if stage=='main':
            entry.dump(out/'runs/one/main/checkpoint_00001.json',dict(valid=True,cmax=10,validated_epoch=time.time()))
        return dict(phase=stage,exit_code=1 if stage=='init' else 0,reason=None)
    monkeypatch.setattr(entry,'execute_phase',fake_execute)
    entry.run(out)
    result=entry.read(out/'runs/one/execution.json')
    assert [c[0] for c in calls]==['init','main']
    assert calls[1][2] is None and calls[1][1]>calls[0][1]
    assert result['construction_fallback'] and result['cmax']==10
    assert result['stages'][0]['exit_code']==1
    assert not result['execution_error']
