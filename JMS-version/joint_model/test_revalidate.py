from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from revalidate import plan,metrics,prepare_reference,read,worker,dump,inventory
from model import Config,Integrated
from seed import construct
from dataclasses import asdict


def test_core_matrix_has_three_seed_pairs_and_no_restricted_bounds():
    cases,pairs=plan('core')
    assert len(pairs)==42
    assert len(pairs)==len(set(pairs))
    assert all(not c['max_pairs'] and not c['max_cycles'] for c in cases.values())
    arms={v for k,v in pairs if k=='n4_H3_mixed_dual'}
    assert {'joint','fixed','legacy','refined','hem','proposed','cold','serial'}<=arms


def test_metrics_empty_and_seed():
    assert metrics({'solutions':0})=={}
    result=construct(Config({'LP1':{'2x2':4},'LP2':{},'LP3':{},'LP4':{}},chambers=(1,),cleaning_interval=10))
    data=metrics(result)
    assert data['route_wait_sum']>=0
    assert data['rhythm_centers']==1
    assert data['early_cleanings']==0
    assert data['legacy_rule_feasible']


def test_common_reference_and_full_space_worker(tmp_path):
    cfg=Config({'LP1':{'4x1':1},'LP2':{},'LP3':{},'LP4':{}},chambers=(1,),cleaning_interval=3)
    (tmp_path/'configs').mkdir();dump(tmp_path/'configs'/'tiny.json',asdict(cfg))
    from run_experiments import digest
    spec=dict(assets=inventory(),case_hashes={'tiny':digest(tmp_path/'configs'/'tiny.json')},policies={'scip':None},training_seed=1,
        spbs_budget=.2,memory_mb=2000,time_limit=2,cut_profile='root_only',
        cells=[dict(id='tiny_joint',case='tiny',variant='joint',seed=1)])
    dump(tmp_path/'campaign.json',spec)
    ref=prepare_reference(tmp_path,'tiny',spec)
    assert read(ref/'certificate.json')['valid']
    worker(tmp_path,'tiny_joint')
    evidence=read(tmp_path/'runs/tiny_joint/evidence.json')
    assert evidence['physical']['valid']
    assert evidence['original_model_check']
    assert read(tmp_path/'runs/tiny_joint/result.json')['full_candidate_space']


@pytest.mark.parametrize('variant',['legacy','refined','quadratic','cold','fixed','partition','waiting_only'])
def test_worker_additional_arms(tmp_path,variant):
    cfg=Config({'LP1':{'4x1':1},'LP2':{},'LP3':{},'LP4':{}},chambers=(1,),cleaning_interval=3)
    (tmp_path/'configs').mkdir();dump(tmp_path/'configs'/'tiny.json',asdict(cfg))
    from run_experiments import digest
    spec=dict(assets=inventory(),case_hashes={'tiny':digest(tmp_path/'configs'/'tiny.json')},policies={'scip':None},training_seed=1,
        spbs_budget=0,memory_mb=2000,time_limit=3,cut_profile='root_only',
        cells=[dict(id='tiny',case='tiny',variant=variant,seed=1)])
    dump(tmp_path/'campaign.json',spec);worker(tmp_path,'tiny')
    assert (tmp_path/'runs/tiny/evidence.json').exists()
    if variant=='legacy':assert read(tmp_path/'runs/tiny/evidence.json')['metrics']['legacy_rule_feasible']
