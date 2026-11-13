"""Exercise low-memory decisions without exhausting RAM or starting a real job."""
import json
from types import SimpleNamespace
import pytest
import large_schedule_resources as memory
import large_schedule_experiments_v2 as exp


@pytest.mark.parametrize('available,stop',[(.4,False),(.25,False),(.249,True),(.01,True)])
def test_guarded_mode_preserves_threshold(available,stop):
    sample=dict(physical_available_fraction=available)
    assert memory.should_stop(memory.policy(),sample)==stop


@pytest.mark.parametrize('disabled,minimum',[(True,.25),(False,0),(True,0)])
def test_observe_only_never_stops_even_at_zero_available(disabled,minimum):
    settings=memory.policy(minimum,disabled)
    sample=dict(physical_available_fraction=0,system_commit_fraction=1)
    assert not settings['memory_guard_enabled']
    assert settings['min_available_fraction']==0
    assert memory.pressure(sample)
    assert not memory.should_stop(settings,sample)


@pytest.mark.parametrize('minimum',[-.1,.5,float('nan'),float('inf')])
def test_invalid_threshold_rejected(minimum):
    with pytest.raises(ValueError):
        memory.policy(minimum)


def test_commit_probe_failure_does_not_create_a_new_stop_rule(monkeypatch):
    def fail():raise OSError('counter unavailable')
    monkeypatch.setattr(memory,'windows_commit',fail)
    sample=memory.snapshot(SimpleNamespace(total=100,available=1))
    assert sample['commit_read_error']=='counter unavailable'
    assert not memory.should_stop(memory.policy(disabled=True),sample)


@pytest.mark.parametrize('disabled',[True,False])
def test_supervisor_obeys_mode_under_low_ram(tmp_path,monkeypatch,capsys,disabled):
    import psutil
    settings=dict(memory.policy(disabled=disabled),gpu_device=0,until_optimal=True,wall_limit=None)
    monkeypatch.setattr(exp,'checked',lambda out:dict(settings=settings))
    monkeypatch.setattr(exp,'status',lambda out:dict(complete=1,failed=0,pending=0))
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(total=100,available=1))
    monkeypatch.setattr(memory,'windows_commit',lambda:dict(
        system_committed_bytes=99,system_commit_limit_bytes=100,system_commit_fraction=.99))
    monkeypatch.setattr(exp.time,'sleep',lambda seconds:None)
    def absent(pid):raise psutil.NoSuchProcess(pid)
    monkeypatch.setattr(psutil,'Process',absent)
    children=[]
    class Child:
        def __init__(self,*args,**kwargs):
            self.pid=999999;self.returncode=0;self.polls=0;self.stopped=False;children.append(self)
            dest=tmp_path/'solve';dest.mkdir()
            exp.dump(dest/'certificate.json',dict(verdict=dict(target_global_optimal=True)))
        def poll(self):
            self.polls+=1
            return None if self.polls==1 else 0
        def wait(self,timeout):return 0
        def terminate(self):self.stopped=True
        def kill(self):self.stopped=True
    monkeypatch.setattr(exp.subprocess,'Popen',Child)
    if not disabled:
        with pytest.raises(RuntimeError,match='RESOURCE_INSUFFICIENT'):
            exp.run(tmp_path)
        assert not children
        return
    exp.run(tmp_path)
    assert len(children)==1 and not children[0].stopped
    record=exp.read(tmp_path/'solve/resources.json')
    assert record['memory_guard_enabled'] is False
    assert record['minimum_system_available_fraction']==.01
    assert record['guard_snapshot'] is None
    assert 'MEMORY_PRESSURE_CONTINUING' in capsys.readouterr().out


def test_native_windows_probe_is_readable():
    if memory.os.name!='nt':
        pytest.skip('Windows system commit API')
    sample=memory.snapshot()
    assert sample['system_commit_limit_bytes']>0
    assert sample['system_committed_bytes']>=0
    assert sample['commit_source']=='GetPerformanceInfo'
