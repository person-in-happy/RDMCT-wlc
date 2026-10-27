from pathlib import Path
from types import SimpleNamespace
import json
import pytest
import evidence_supplement as e
import low_memory_evidence as low
from experiment_console import can_start
from memory_policy import process_limit,required_memory,wait_message


def test_admission_uses_enforced_rss_not_scip_accounting():
    cell={'case':'a','learned':False};spec={'memory_mb':18944,'process_memory_mb':14336}
    assert required_memory(spec)==16384
    assert can_start(cell,{},16384,18944,2048,1,14336)
    assert not can_start(cell,{},16383,18944,2048,1,14336)
    assert not can_start(cell,{},18500,18944,2048,1) # old 23833.6 gate


def test_active_workers_reserve_growth_to_the_rss_cap():
    a={'x':{'cell':{'case':'a','learned':False},'rss_mb':4096}}
    c={'case':'b','learned':False}
    assert not can_start(c,a,16384,18944,2048,1,14336)
    assert can_start(c,a,26624,18944,2048,1,14336)


def test_wait_reason_exposes_gap_and_pauses_eta():
    assert 'missing=384MiB' in wait_message(16000,16384,300,300)
    assert 'ETA paused' in wait_message(16000,16384,300,300)


def test_retains_only_whole_mode_groups_regardless_of_objective():
    _,pairs=e.matrix('mode24');cells=[dict(id=f'{case}__s{s}__{arm}',case=case,seed=s,variant=arm) for s in (1,2,3) for case,arm in pairs]
    done={c['id'] for c in cells[:28]}
    pending,retained=low.split_mode_groups(cells,done)
    assert len(retained)==27 and len(pending)==45
    assert cells[27] in pending
    assert len(set(retained)|{c['id'] for c in pending})==72


def test_refuses_incomplete_comparison_matrix():
    with pytest.raises(ValueError,match='three recipes'):
        low.split_mode_groups([dict(id='one',case='n24_H3_4x1_dual',seed=1,variant='joint')],set())


def test_refuses_parent_with_a_live_worker(tmp_path,monkeypatch):
    proc=SimpleNamespace(pid=12345,info={'name':'python.exe','cmdline':['python','revalidate.py','worker','--campaign',str(tmp_path)]})
    monkeypatch.setattr(low.psutil,'process_iter',lambda fields:[proc])
    with pytest.raises(RuntimeError,match='Parent campaign still active'):low.require_idle(tmp_path.resolve())


def test_new_protocol_freezes_the_actual_rss_ceiling(tmp_path,monkeypatch):
    out=tmp_path/'campaign';monkeypatch.setattr(e,'campaign_path',lambda value:Path(value))
    low.prepare(out,'fixed')
    spec,contract=e.checked(out)
    assert spec['memory_mb']==18944 and spec['process_memory_mb']==14336
    assert contract['settings']['process_memory_mb']==14336
    assert required_memory(spec,contract['settings']['jobs'],contract['reserve_mb'])==16384
    assert spec['memory_wait_seconds']==300
    low.prepare(out,'fixed')
    (out/'preparation_pending.json').write_text('{}')
    with pytest.raises(RuntimeError,match='preparation was interrupted'):e.checked(out)


def scheduler_fixture(tmp_path,monkeypatch,available):
    import experiment_console as console
    import revalidate
    spec=dict(memory_mb=18944,process_memory_mb=14336,memory_wait_seconds=300,time_limit=300,wall_limit=3600,
        cells=[dict(id='one',case='case',variant='joint',seed=1)])
    (tmp_path/'campaign.json').write_text(json.dumps(spec))
    monkeypatch.setattr(revalidate,'verify',lambda out:spec)
    monkeypatch.setattr(console.psutil if hasattr(console,'psutil') else low.psutil,'virtual_memory',lambda:SimpleNamespace(available=available*1024**2,total=32768*1024**2))
    args=SimpleNamespace(campaign=str(tmp_path),jobs=1,gpu_slots=1,reserve_mb=2048,retry_failed=False,refresh=15)
    return console,args


def test_idle_ram_timeout_preserves_pending_cells(tmp_path,monkeypatch):
    console,args=scheduler_fixture(tmp_path,monkeypatch,16000)
    import itertools
    clock=itertools.count(0,301)
    monkeypatch.setattr(console.time,'monotonic',lambda:next(clock))
    with pytest.raises(RuntimeError,match='RAM wait expired'):console.run(args)
    assert json.loads((tmp_path/'progress.json').read_text())=={'cells':{}}
    assert (tmp_path/'resource_wait.json').exists()
    assert not list(tmp_path.rglob('failure.json'))


def test_scheduler_enforces_lower_rss_cap(tmp_path,monkeypatch):
    console,args=scheduler_fixture(tmp_path,monkeypatch,18000)
    import revalidate
    class Worker:
        pid=12345
        stopped=False
        def poll(self):return 1 if self.stopped else None
        def terminate(self):self.stopped=True
        def wait(self,timeout=None):return 1
    worker=Worker()
    monkeypatch.setattr(console.subprocess,'Popen',lambda *a,**k:worker)
    monkeypatch.setattr(low.psutil,'Process',lambda pid:SimpleNamespace(memory_info=lambda:SimpleNamespace(rss=14337*1024**2)))
    monkeypatch.setattr(console.time,'sleep',lambda seconds:None)
    monkeypatch.setattr(revalidate,'summarize',lambda out:{'states':{'execution_failed':1}})
    monkeypatch.setattr(console,'display',lambda *a,**k:None)
    console.run(args)
    assert worker.stopped
    failure=json.loads((tmp_path/'runs/one/failure.json').read_text())
    assert failure['reason']=='process_memory_guard'


def test_continuation_copies_references_and_freezes_remaining_groups(tmp_path,monkeypatch):
    parent=tmp_path/'parent';out=tmp_path/'child'
    monkeypatch.setattr(e,'campaign_path',lambda value:Path(value))
    e.prepare(SimpleNamespace(campaign=str(parent),suite='mode24',memory_mb=18944,jobs=1))
    old=e.read(parent/'campaign.json');old_hash=e.digest(parent/'campaign.json')
    pending,retained=low.split_mode_groups(old['cells'],{c['id'] for c in old['cells'][:28]})
    audit=parent/'audit.json';audit.write_text('{}')
    transition=dict(parent=str(parent),parent_audit=str(audit),parent_audit_sha256=e.digest(audit),
        retained_external_cells=retained,rerun_partial_group_cells=[old['cells'][27]['id']])
    for key in old['case_hashes']:
        ref=parent/'references'/key;ref.mkdir(parents=True)
        (ref/'common.json').write_text('{"values":{}}')
        e.dump(ref/'certificate.json',dict(valid=True,files={'common.json':e.digest(ref/'common.json')}))
    def receipt(root,key,spec):
        ref=root/'references'/key;cert=e.read(ref/'certificate.json')
        assert all(e.digest(ref/n)==sha for n,sha in cert['files'].items())
    monkeypatch.setattr(e,'reference_receipt',receipt)
    monkeypatch.setattr(low,'parent_plan',lambda p,s:(old,pending,transition))
    low.prepare(out,'mode24',parent)
    spec,_=e.checked(out)
    assert len(spec['cells'])==45 and e.digest(parent/'campaign.json')==old_hash
    assert not (out/'runs').exists() # Old runs must not masquerade as new-budget runs.
    assert all((out/'references'/k/'common.json').exists() for k in spec['case_hashes'])
    assert not (out/'preparation_pending.json').exists()
    (out/'continuation.json').write_text('{}')
    with pytest.raises(RuntimeError,match='Continuation record changed'):e.checked(out)
