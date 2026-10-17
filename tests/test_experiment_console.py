import importlib.util
import json
import pytest
from pathlib import Path
from datetime import datetime,timezone

path=Path(__file__).resolve().parents[1]/'JMS-version/tools/experiment_console.py'
spec=importlib.util.spec_from_file_location('experiment_console',path)
console=importlib.util.module_from_spec(spec);spec.loader.exec_module(console)

def test_adoption_refuses_orphan_worker(tmp_path,monkeypatch):
    import psutil
    from types import SimpleNamespace
    worker=SimpleNamespace(pid=987654,info=dict(name='python.exe',cmdline=[
        'python','revalidate.py','worker','--campaign',str(tmp_path),'--cell','a']))
    monkeypatch.setattr(psutil,'process_iter',lambda attrs:[worker])
    with pytest.raises(RuntimeError,match='live process'):
        console.ensure_idle(tmp_path.resolve())

def test_adoption_preserves_evidence_and_archives_stale_state(tmp_path,monkeypatch):
    monkeypatch.setattr(console,'ensure_idle',lambda out:None)
    def dump(path,value):path.write_text(json.dumps(value),encoding='utf-8')
    prior={'cells':{'a':{'state':'running','started_utc':'2026-10-16T00:00:00+00:00'},
                    'b':{'state':'running'}}}
    dump(tmp_path/'progress.json',prior);dump(tmp_path/'stopped.json',{'error':'missing psutil'})
    dest=tmp_path/'runs'/'a';dest.mkdir(parents=True)
    dump(dest/'evidence.json',{'complete':True,'completed_utc':'2026-10-16T00:05:00+00:00'})
    original=(dest/'evidence.json').read_bytes()
    console.adopt_stopped(tmp_path,{'cells':[{'id':'a'},{'id':'b'}]},dump)
    assert (dest/'evidence.json').read_bytes()==original
    assert not (tmp_path/'stopped.json').exists()
    p=console.read(tmp_path/'progress.json')['cells']
    assert p['a']['state']=='complete' and p['a']['exit_code'] is None
    assert p['b']['state']=='pending'
    archived=list((tmp_path/'scheduler_transitions').iterdir())[0]
    assert console.read(archived/'progress.json')==prior
    assert console.read(archived/'transition.json')['retained_cells']==['a']

def test_adoption_requires_failed_supervisor_record(tmp_path,monkeypatch):
    monkeypatch.setattr(console,'ensure_idle',lambda out:None)
    with pytest.raises(RuntimeError,match='stopped.json'):
        console.adopt_stopped(tmp_path,{'cells':[]},lambda *args:None)


def test_reference_and_gpu_conflicts_are_serialized():
    active={'one':dict(cell=dict(case='same',learned=True),rss_mb=100)}
    assert not console.can_start(dict(case='same',learned=False),active,30000,6000,4096,1)
    assert not console.can_start(dict(case='other',learned=True),active,30000,6000,4096,1)
    assert console.can_start(dict(case='other',learned=False),active,30000,6000,4096,1)


def test_memory_accounts_for_active_job_growth():
    active={'one':dict(cell=dict(case='same',learned=False),rss_mb=100)}
    # Free RAM can fit one worker, but not its reserved growth plus another.
    assert not console.can_start(dict(case='other',learned=False),active,15000,6000,4096,1)
    assert console.can_start(dict(case='other',learned=False),{},15000,6000,4096,1)


def test_eta_uses_matching_case_and_variant_history():
    cells=[dict(id=f'x{i}',case='a',variant='joint') for i in range(3)]
    progress={'cells':{'x0':dict(state='complete',started_utc='2026-10-16T00:00:00+00:00',ended_utc='2026-10-16T00:05:00+00:00'),
        'x1':dict(state='running',started_utc='2026-10-16T00:05:00+00:00')}}
    status=console.snapshot(dict(cells=cells,time_limit=300),progress,datetime(2026,10,16,0,7,tzinfo=timezone.utc))
    assert status['done']==1 and status['remaining']==2
    assert status['serial_seconds']==480


def test_parallel_runner_updates_completion_without_real_solves(tmp_path,monkeypatch):
    import sys,json,psutil
    from types import SimpleNamespace
    sys.path.insert(0,str(console.JOINT))
    import revalidate
    cells=[dict(id='a1',case='a',variant='joint',seed=1),dict(id='a2',case='a',variant='refined',seed=1),
        dict(id='b',case='b',variant='joint',seed=1),dict(id='c',case='c',variant='hem',seed=1),dict(id='d',case='d',variant='proposed',seed=1)]
    spec=dict(cells=cells,time_limit=10,memory_mb=6000,wall_limit=100)
    (tmp_path/'campaign.json').write_text(json.dumps(spec),encoding='utf-8')
    monkeypatch.setattr(revalidate,'verify',lambda out:spec)
    monkeypatch.setattr(revalidate,'summarize',lambda out:{'states':{'complete':5}})
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=32*1024**3,total=32*1024**3))
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(memory_info=lambda:SimpleNamespace(rss=0)))
    live={};peak=[]
    class Child:
        def __init__(self,cmd,**kwargs):
            self.cid=cmd[-1];self.pid=len(peak)+1;self.n=0;self.done=False
            cell=next(c for c in cells if c['id']==self.cid)
            assert all(c['case']!=cell['case'] for c in live.values())
            if cell['variant'] in ('hem','proposed'):assert not any(c['variant'] in ('hem','proposed') for c in live.values())
            live[self.cid]=cell;peak.append(len(live))
        def poll(self):
            if self.done:return 0
            self.n+=1
            if self.n<3:return None
            self.done=True;live.pop(self.cid)
            dest=tmp_path/'runs'/self.cid;dest.mkdir(parents=True,exist_ok=True)
            (dest/'evidence.json').write_text('{}')
            return 0
        def terminate(self):self.done=True;live.pop(self.cid,None)
        def wait(self,**kwargs):return 0
    monkeypatch.setattr(console.subprocess,'Popen',Child)
    monkeypatch.setattr(console.time,'sleep',lambda _:None)
    console.run(SimpleNamespace(campaign=str(tmp_path),jobs=2,gpu_slots=1,reserve_mb=4096,retry_failed=False,refresh=15))
    progress=json.loads((tmp_path/'progress.json').read_text())
    assert max(peak)==2
    assert len(progress['cells'])==5
    assert all(c['state']=='complete' for c in progress['cells'].values())
