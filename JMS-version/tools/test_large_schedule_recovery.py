"""Recovery must preserve the model/proof gates and stop on commit pressure."""
from types import SimpleNamespace

import pytest

import large_schedule_experiments_v3 as exp
import large_schedule_recovery as recovery


def sample(available=.4, commit_gib=20):
    return dict(physical_total_bytes=32*1024**3,
                physical_available_bytes=int(available*32*1024**3),
                physical_available_fraction=available,
                system_committed_bytes=int((168-commit_gib)*1024**3),
                system_commit_limit_bytes=168*1024**3,
                system_commit_available_bytes=int(commit_gib*1024**3))


@pytest.mark.parametrize('available,commit_gib,reason', [
    (.4, 20, None),
    (.05, 8, None),
    (.4, 7.99, 'system_commit_memory_guard'),
    (.049, 20, 'system_available_memory_guard'),
])
def test_physical_and_commit_guards_are_independent(available, commit_gib, reason):
    assert recovery.stop_reason(recovery.policy(), sample(available, commit_gib)) == reason


def test_zero_physical_threshold_keeps_explicit_commit_guard():
    settings = recovery.policy(minimum=0)
    assert recovery.should_stop(settings, sample(0, 1))
    assert not recovery.should_stop(recovery.policy(disabled=True), sample(0, 0))


def test_required_commit_counter_cannot_silently_disappear():
    data = sample()
    del data['system_commit_available_bytes']
    assert recovery.stop_reason(recovery.policy(), data) == 'system_commit_telemetry_unavailable'
    assert recovery.stop_reason(recovery.policy(min_commit_available_gib=0), data) is None


@pytest.mark.parametrize('value', [-1, float('inf'), float('nan')])
def test_invalid_commit_reserve_is_rejected(value):
    with pytest.raises(ValueError, match='Commit reserve'):
        recovery.policy(min_commit_available_gib=value)


def test_low_commit_prevents_worker_launch(tmp_path, monkeypatch):
    settings = dict(recovery.policy(), gpu_device=0, until_optimal=True, wall_limit=None)
    monkeypatch.setattr(exp, 'checked', lambda out: dict(settings=settings))
    monkeypatch.setattr(recovery, 'snapshot', lambda vm=None: sample(.4, 1))
    def forbidden(*args, **kwargs):
        pytest.fail('No worker may start below the system commit reserve')
    monkeypatch.setattr(exp.subprocess, 'Popen', forbidden)
    with pytest.raises(RuntimeError, match='system_commit_memory_guard'):
        exp.run(tmp_path)
    assert not (tmp_path/'solve').exists()


def test_running_commit_guard_preserves_failure_evidence(tmp_path, monkeypatch):
    settings = dict(recovery.policy(), gpu_device=0, until_optimal=True, wall_limit=None)
    monkeypatch.setattr(exp, 'checked', lambda out: dict(settings=settings))
    samples = iter([sample(.4, 20), sample(.4, 1)])
    monkeypatch.setattr(recovery, 'snapshot', lambda vm=None: next(samples))
    child = SimpleNamespace(pid=99999999, returncode=1, stopped=False)
    child.poll = lambda: None
    child.wait = lambda timeout: 1
    child.terminate = lambda: setattr(child, 'stopped', True)
    monkeypatch.setattr(exp.subprocess, 'Popen', lambda *args, **kwargs: child)
    with pytest.raises(RuntimeError, match='system_commit_memory_guard'):
        exp.run(tmp_path)
    assert child.stopped
    assert exp.read(tmp_path/'solve/failure.json')['reason'] == 'system_commit_memory_guard'
    assert not (tmp_path/'solve/certificate.json').exists()


def test_recovery_keeps_actual_small_schedule_optimum():
    cfg = exp.configuration(SimpleNamespace(size=1, recipe='4x1', cleaning_interval=3, dummy_count=8))
    records = []
    for recover in (False, True):
        x = exp.Integrated(cfg)
        model = x.model
        try:
            model.hideOutput()
            model.setRealParam('limits/time', 15)
            if recover:
                exp.configure_stopping(model, dict(until_optimal=False, time_limit=15))
                assert {k: model.getParam(k) for k in recovery.SCIP_PARAMETERS} == recovery.SCIP_PARAMETERS
            model.optimize()
            result = x.result()
            assert str(model.getStatus()) == 'optimal'
            assert model.checkSol(model.getBestSol(), completely=True, original=True)
            assert exp.validate(result)['valid']
            assert not x.bounded and cfg.max_pairs == cfg.max_cycles == 0
            records.append((x.original_dimensions, result['cmax']))
        finally:
            model.freeProb()
    assert records[0][0] == records[1][0]
    assert records[0][1] == pytest.approx(records[1][1], abs=2e-4)


def test_phase_report_does_not_call_presolve_export(tmp_path):
    assert recovery.solver_stage(tmp_path) == 'building'
    (tmp_path/'build.json').write_text('{}')
    (tmp_path/'solver.log').write_text('presolving:\n(round 1, fast) 0 del vars\n')
    assert recovery.solver_stage(tmp_path) == 'presolving'
