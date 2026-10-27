import json,hashlib
import pytest
from supplement_memory_guard import require_unfailed_budget

def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v),encoding='utf-8')
def setup(tmp_path,reason='process_memory_guard'):
    p=tmp_path/'supp_failed';cfg={'load_ports':{'LP1':{'2x2':24}}};assets={'model':'abc'}
    settings=dict(time_limit=300,wall_limit=3600,spbs_budget=20)
    write(p/'configs/case.json',cfg)
    write(p/'campaign.json',dict(assets=assets,memory_mb=14336,case_hashes={'case':hashlib.sha256((p/'configs/case.json').read_bytes()).hexdigest()},**settings))
    log=p/'preflight_logs/reason.log';log.parent.mkdir(exist_ok=True);log.write_text('Common start completion failed: memlimit')
    write(p/'preflight_logs/case.failure.json',dict(reason=reason,log=str(log)))
    return {'case':cfg},assets,settings

@pytest.mark.parametrize('reason',['process_memory_guard','exit_1'])
def test_lower_equal_rejected_and_higher_not_certified(tmp_path,reason):
    cases,assets,settings=setup(tmp_path,reason)
    for budget in (12544,14336):
        with pytest.raises(RuntimeError,match='No reference or solver started'):require_unfailed_budget(tmp_path,cases,assets,settings,budget)
    require_unfailed_budget(tmp_path,cases,assets,settings,16000)

def test_changed_model_case_or_protocol_is_different(tmp_path):
    cases,assets,settings=setup(tmp_path)
    require_unfailed_budget(tmp_path,cases,{'model':'new'},settings,12544)
    require_unfailed_budget(tmp_path,{'case':{'different':1}},assets,settings,12544)
    require_unfailed_budget(tmp_path,cases,assets,dict(settings,spbs_budget=0),12544)

@pytest.mark.parametrize('reason',['foreground_interrupted','reference_wall_guard','validation_failed'])
def test_other_failures_do_not_establish_memory_gate(tmp_path,reason):
    cases,assets,settings=setup(tmp_path,reason)
    require_unfailed_budget(tmp_path,cases,assets,settings,12544)
