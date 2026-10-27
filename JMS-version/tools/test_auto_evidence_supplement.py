from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import auto_evidence_supplement as a


@pytest.fixture(autouse=True)
def isolated_history(monkeypatch,tmp_path):
    from supplement_memory_guard import require_unfailed_budget
    monkeypatch.setattr(a,'memory_gate',lambda cases,settings,memory:require_unfailed_budget(tmp_path,cases,a.e.inventory(),settings,memory))


@pytest.mark.parametrize('available,jobs,cap',[(14000,1,24000),(14000,2,24000),(60000,2,24000),(32000,2,6000)])
def test_selection_preserves_reserves_and_caps(available,jobs,cap):
    r=a.allocation(available,jobs,cap)
    assert 1024<=r['memory_mb']<=cap
    assert r['required_mib']<=.9*available
    assert r['memory_mb']==cap or r['memory_mb']%256==0


def test_insufficient_memory_is_not_silently_allocated():
    with pytest.raises(RuntimeError):a.allocation(2500,2,24000)


def test_prepare_records_and_reuses_memory_when_available_changes(tmp_path,monkeypatch):
    e=a.e
    monkeypatch.setattr(e,'campaign_path',lambda path:Path(path))
    monkeypatch.setattr(a.psutil,'virtual_memory',lambda:SimpleNamespace(available=14000*1024**2,total=32000*1024**2))
    out=tmp_path/'campaign'
    def args(memory=None,jobs=None):return SimpleNamespace(campaign=str(out),suite='mode24',memory_mb=memory,jobs=jobs)
    a.prepare(args())
    original=(out/'campaign.json').read_bytes();receipt=(out/'memory_selection.json').read_bytes()
    selected=e.read(out/'campaign.json')['memory_mb']
    assert selected==a.allocation(14000,1,24000)['memory_mb']
    assert len(e.read(out/'campaign.json')['cells'])==72
    monkeypatch.setattr(a.psutil,'virtual_memory',lambda:SimpleNamespace(available=4000*1024**2,total=32000*1024**2))
    a.prepare(args())
    assert (out/'campaign.json').read_bytes()==original
    assert (out/'memory_selection.json').read_bytes()==receipt
    with pytest.raises(RuntimeError,match='Protocol changed'):a.prepare(args(6000))


def test_historical_explicit_budget_is_not_replaced(tmp_path,monkeypatch):
    e=a.e;monkeypatch.setattr(e,'campaign_path',lambda path:Path(path))
    out=tmp_path/'historical'
    args=SimpleNamespace(campaign=str(out),suite='mode24',memory_mb=24000,jobs=1)
    e.prepare(args)
    monkeypatch.setattr(a,'allocation',lambda *args:pytest.fail('Frozen campaign must not resample'))
    a.prepare(SimpleNamespace(campaign=str(out),suite='mode24',memory_mb=None,jobs=None))
    assert e.read(out/'campaign.json')['memory_mb']==24000
    assert not (out/'memory_selection.json').exists()
