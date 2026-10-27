"""Scientific gates and restart behavior; no production campaign is touched."""
from pathlib import Path
from types import SimpleNamespace
from dataclasses import asdict
import json
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_supplement as e
from supplement_protocol import balanced_reference


def test_registered_matrices_have_paired_controls_and_full_candidates():
    expected = dict(fixed=12, mode24=72, scale32=9, gantt16=4,
                    rhythm=48, cleaning=96, doe=180, ood=81)
    for suite, count in expected.items():
        cases, pairs = e.matrix(suite)
        assert len(pairs) * len(e.defaults(suite)['seeds']) == count
        assert len(pairs) == len(set(pairs))
        assert all(c['max_pairs'] == c['max_cycles'] == 0 for c in cases.values())
    cases, pairs = e.matrix('mode24')
    for h in range(3, 11):
        assert all((f'n24_H{h}_{recipe}_dual', 'joint') in pairs
                   for recipe in ('4x1', '2x2', 'mixed'))


def test_rhythm_is_measurable_and_cleaning_start_is_shared():
    for cfg in e.matrix('rhythm')[0].values():
        r = balanced_reference(e.Config(**cfg))
        assert e.validate(r)['valid']
        assert e.metrics(r)['rhythm_centers'] == 2
    for cfg in e.matrix('cleaning')[0].values():
        r = balanced_reference(e.Config(**cfg))
        assert e.validate(r)['valid']
        assert e.metrics(r)['legacy_rule_feasible']
    assert e.defaults('cleaning')['spbs_budget'] == 0


def test_limits_and_conditional_optima_never_become_global_proofs():
    row = dict(has_solution=True, full_candidate_space=True, status='optimal',
               upper=10, lower=10, gap=0)
    assert e.certified_optimal(row)
    for change in (dict(status='timelimit'), dict(full_candidate_space=False),
                   dict(lower=None), dict(lower=-1e20), dict(lower=9), dict(gap=.1)):
        assert not e.certified_optimal(row | change)


@pytest.mark.parametrize('reason', ['process_memory_guard', 'exit_1', 'cell_wall_guard',
                                  'reference_wall_guard', 'validation_failed'])
def test_only_manual_interruption_is_retryable(reason):
    assert not e.eligible_interruption(dict(reason=reason))
    assert e.eligible_interruption(dict(reason='foreground_interrupted'))


def test_prepare_freezes_protocol_and_rejects_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(e, 'campaign_path', lambda p: Path(p))
    out = tmp_path / 'frozen'
    a = SimpleNamespace(campaign=str(out), suite='fixed', memory_mb=6000, jobs=2)
    e.prepare(a)
    before = (out / 'campaign.json').read_bytes()
    e.prepare(a)
    assert (out / 'campaign.json').read_bytes() == before
    with pytest.raises(RuntimeError, match='Protocol changed'):
        e.prepare(SimpleNamespace(**(vars(a) | dict(jobs=1))))
    cfg = out / 'configs/n4_H3_mixed_dual.json'
    data = e.read(cfg)
    data['full_time'] += 1
    e.dump(cfg, data)
    with pytest.raises(RuntimeError, match='Configuration changed'):
        e.checked(out)


def test_real_tiny_campaign_reference_run_audit_resume(tmp_path, monkeypatch):
    # A tiny actual MILP verifies the wrapper-to-frozen-worker contract.
    # Output is inside the repository so subprocess path checks remain active.
    import tempfile
    test_root = e.ROOT / 'JMS-version/results/command_entry_tests'
    test_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='tiny_', dir=test_root)) / 'campaign'
    cfg = asdict(e.Config({'LP1': {'4x1': 1}, 'LP2': {}, 'LP3': {}, 'LP4': {}},
                         chambers=(1,), cleaning_interval=3))
    monkeypatch.setattr(e, 'matrix', lambda suite: ({'tiny': cfg}, [('tiny', 'joint')]))
    monkeypatch.setattr(e, 'defaults', lambda suite: dict(memory_mb=2000, jobs=1,
        time_limit=2, wall_limit=120, spbs_budget=0, seeds=[1]))
    e.prepare(SimpleNamespace(campaign=str(out), suite='fixed', memory_mb=None, jobs=None))
    with pytest.raises(FileNotFoundError):
        e.run(out)
    e.preflight(out)
    e.run(out)
    report = e.audit(out)
    assert report['coverage_complete'] and report['feasible'] == 1
    result = out / 'runs/tiny__s1__joint/result.json'
    before = e.digest(result)
    e.run(out, resume=True)
    assert e.digest(result) == before
    assert not (out / 'interrupted_attempts').exists()
    # Simulate a saved interruption without overwriting the completed test run.
    preserved = out / 'test_completed_before_simulated_interruption'
    result.parent.rename(preserved)
    result.parent.mkdir()
    e.dump(result.parent / 'failure.json', dict(reason='foreground_interrupted'))
    e.run(out, resume=True)
    assert e.audit(out)['coverage_complete']
    assert list((out / 'interrupted_attempts').glob('tiny__s1__joint_resume_*'))
    assert e.digest(preserved / 'result.json') == before
    # A corrupted saved result must never be silently skipped on resume.
    original = result.read_bytes()
    result.write_bytes(original + b' ')
    with pytest.raises(RuntimeError, match='changed evidence'):
        e.run(out, resume=True)
    result.write_bytes(original)
    print('Test-only MILP evidence: ' + str(out))
