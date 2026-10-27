from types import SimpleNamespace
import pytest
import fixed_evidence_supplement as f

def test_missing_budget_cannot_trigger_automatic_allocation(tmp_path):
    with pytest.raises(ValueError,match='Automatic allocation is disabled'):
        f.check_budget(tmp_path/'new',None,None,'mode24',50000)

def test_fixed_16g_fits_observed_ram_but_24g_and_two_workers_do_not(tmp_path):
    assert f.check_budget(tmp_path/'new',16384,1,'mode24',22505)==(16384,1)
    for memory,jobs in [(24000,1),(16384,2)]:
        with pytest.raises(RuntimeError,match='No budget reduction'):
            f.check_budget(tmp_path/'new',memory,jobs,'mode24',22505)

def test_existing_budget_preserved_and_changes_rejected(tmp_path):
    f.e.dump(tmp_path/'supplement.json',dict(contract=dict(suite='mode24',settings=dict(memory_mb=16384,jobs=1))))
    assert f.check_budget(tmp_path,None,None,'mode24',22505)==(16384,1)
    with pytest.raises(ValueError,match='Frozen budget differs'):
        f.check_budget(tmp_path,24000,1,'mode24',50000)

def test_new_fixed_prepare_never_calls_allocator(tmp_path,monkeypatch):
    import auto_evidence_supplement as a
    monkeypatch.setattr(a,'allocation',lambda *args:pytest.fail('Automatic allocator called'))
    monkeypatch.setattr(a,'memory_gate',lambda *args:None)
    monkeypatch.setattr(a.e,'campaign_path',lambda p:__import__('pathlib').Path(p))
    out=tmp_path/'explicit'
    f.prepare(SimpleNamespace(campaign=str(out),suite='mode24',memory_mb=16384,jobs=1))
    assert f.e.read(out/'campaign.json')['memory_mb']==16384
    assert f.e.read(out/'memory_selection.json')['policy']=='explicit'
