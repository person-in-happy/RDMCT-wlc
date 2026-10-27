from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import available_evidence_supplement as a


@pytest.mark.parametrize('available,jobs', [(20382, 1), (60000, 1), (60000, 2)])
def test_uses_largest_safe_quantized_budget_without_fixed_cap(available, jobs):
    r = a.allocation(available, jobs)
    assert r['required_mib'] <= available
    assert (r['memory_mb'] + 256) * 1.15 * jobs + 2048 > available
    assert r['cap_mb'] is None
    if available == 60000 and jobs == 1:
        assert r['memory_mb'] > 24000


@pytest.mark.parametrize('available,jobs', [(2000, 1), (float('nan'), 1), (32000, 0)])
def test_invalid_or_insufficient_memory_rejected(available, jobs):
    with pytest.raises((RuntimeError, ValueError)):
        a.allocation(available, jobs)


def args(out, action='prepare', jobs=None):
    return SimpleNamespace(campaign=str(out), suite='mode24', jobs=jobs, action=action)


def test_history_rejection_does_not_create_campaign(tmp_path, monkeypatch):
    out = tmp_path / 'blocked'
    monkeypatch.setattr(a.e, 'campaign_path', Path)
    monkeypatch.setattr(a.psutil, 'virtual_memory', lambda: SimpleNamespace(available=20382 * 1024**2))
    def reject(*unused):
        raise RuntimeError('Known reference memory failure')
    monkeypatch.setattr(a, 'gate', reject)
    with pytest.raises(RuntimeError, match='Known reference'):
        a.prepare(args(out))
    assert not out.exists()


def test_prepare_freezes_budget_and_never_resamples_existing_campaign(tmp_path, monkeypatch):
    out = tmp_path / 'frozen'
    monkeypatch.setattr(a.e, 'campaign_path', Path)
    monkeypatch.setattr(a, 'gate', lambda *unused: None)
    monkeypatch.setattr(a.psutil, 'virtual_memory', lambda: SimpleNamespace(available=60000 * 1024**2, total=65536 * 1024**2))
    a.prepare(args(out))
    before = {f: (out / f).read_bytes() for f in ('campaign.json', 'memory_selection.json')}
    assert a.e.read(out / 'campaign.json')['memory_mb'] > 24000
    assert (out / 'frozen_code/available_evidence_supplement.py').is_file()
    monkeypatch.setattr(a, 'allocation', lambda *unused: pytest.fail('Must not resample'))
    monkeypatch.setattr(a.psutil, 'virtual_memory', lambda: SimpleNamespace(available=62000 * 1024**2, total=65536 * 1024**2))
    a.prepare(args(out))
    assert all((out / f).read_bytes() == data for f, data in before.items())
    with pytest.raises(ValueError, match='Concurrency'):
        a.prepare(args(out, jobs=2))
    monkeypatch.setattr(a.psutil, 'virtual_memory', lambda: SimpleNamespace(available=10000 * 1024**2, total=65536 * 1024**2))
    with pytest.raises(RuntimeError, match='no resampling'):
        a.prepare(args(out))


def test_check_is_read_only(tmp_path, monkeypatch, capsys):
    out = tmp_path / 'check_only'
    monkeypatch.setattr(a.e, 'campaign_path', Path)
    monkeypatch.setattr(a, 'gate', lambda *unused: None)
    monkeypatch.setattr(a.psutil, 'virtual_memory', lambda: SimpleNamespace(available=60000 * 1024**2))
    monkeypatch.setattr(sys, 'argv', ['available_evidence_supplement.py', 'check', '--suite', 'mode24', '--campaign', str(out)])
    a.main()
    assert not out.exists()
    assert 'no files created or solver started' in capsys.readouterr().out
