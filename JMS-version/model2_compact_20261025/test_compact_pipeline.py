from pathlib import Path
from dataclasses import asdict
import json
import pytest
from model import Config,Integrated
from run_experiments import ports,solve,assets
from seed import construct
from reference_completion import complete_reference


@pytest.mark.parametrize('source',['single','dual'])
def test_active_reference_lifts_to_full_candidate_model(source):
    cfg=Config(ports(4,'mixed'),source=source)
    x=Integrated(cfg)
    try:
        serial,common,levels,receipt=complete_reference(x,construct(cfg),2000,0)
        assert not x.bounded
        assert receipt['full_pairs']==22 and receipt['full_cycles_per_chamber']==12
        assert receipt['active_pairs']<receipt['full_pairs']
        assert receipt['complete_model_check'] and receipt['independent_physical_check']
        assert not levels and serial==common
    finally:x.model.freeProb()


@pytest.mark.parametrize('objective',['full','waiting_only','quadratic'])
def test_main_and_refinement_accept_eliminated_wait_variables(tmp_path,objective):
    cfg=Config(ports(1,'4x1'),chambers=(1,),dummy_count=4)
    path=tmp_path/'config.json';path.write_text(json.dumps(asdict(cfg)),encoding='utf-8')
    solve(path,tmp_path/'run',time_limit=2,stage2_limit=2,memory_mb=2000,
          initialization='serial',initialization_budget=0,refinement_objective=objective)
    primary=json.loads((tmp_path/'run/phase1.json').read_text(encoding='utf-8'))
    result=json.loads((tmp_path/'run/result.json').read_text(encoding='utf-8'))
    assert primary['original_model_check'] and primary['validation']['valid']
    assert result['original_model_check'] and result['validation']['valid']
    assert result['full_candidate_space']
    assert result['cmax']<=primary['cmax']+2e-4


def test_campaign_assets_and_worker_use_isolated_implementation():
    import evidence_supplement as e
    import experiment_console as console
    here=Path(__file__).resolve().parent
    assert e.JOINT==here and console.JOINT==here and e.CONSOLE==here/'experiment_console.py'
    names=assets()
    assert any(k.endswith('model2_compact_20261025/reference_completion.py') or k.endswith('model2_compact_20261025\\reference_completion.py') for k in names)
    assert all('JMS-version\\joint_model\\model.py' not in k for k in names)


def test_campaign_freezes_compact_sources_and_rejects_changed_input(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import evidence_supplement as e
    out=tmp_path/'campaign'
    monkeypatch.setattr(e,'campaign_path',lambda value:Path(value))
    args=SimpleNamespace(campaign=str(out),suite='fixed',memory_mb=6000,jobs=1)
    e.prepare(args)
    spec,contract=e.checked(out)
    for relative,sha in spec['assets'].items():
        assert e.digest(out/'frozen_code'/relative)==sha
    assert contract['settings']['memory_mb']==6000
    e.prepare(args)  # Reuse must preserve the protocol and source snapshots.
    case=next(iter(spec['case_hashes']))
    path=out/'configs'/f'{case}.json'
    cfg=json.loads(path.read_text(encoding='utf-8'));cfg['cleaning_interval']+=1
    path.write_text(json.dumps(cfg),encoding='utf-8')
    with pytest.raises(RuntimeError,match='Configuration changed'):
        e.checked(out)
