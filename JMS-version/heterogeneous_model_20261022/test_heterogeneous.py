"""Small, bounded correctness tests; no formal 100-wafer solver is launched."""
from pathlib import Path
from dataclasses import replace
import copy,json,sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model import Config,Integrated
from recipes import validate_groups
from seed import construct,constrain_seed
from validate import validate
from joint_pairing_model import products_from_load_ports,add_joint_pairing
from joint_chamber_cycle_model import add_chamber_cycles
from scip_imports import scip
from experiment import configuration


def config(mode='4x1',n=3):
    ports={f'LP{i}':{'4x1':0,'2x2':0} for i in range(1,5)};ports['LP1'][mode]=n
    cfg=Config(ports)
    cfg.processing_groups={f'G{i+1}':{'wafers':[f'LP1_W{i+1}'],'4x1':d,'2x2':d} for i,d in enumerate((80,180,90)[:n])}
    return cfg


@pytest.mark.parametrize('mode',['4x1','2x2'])
def test_constructed_routes_and_two_exposure_durations(mode):
    cfg=config(mode);result=construct(cfg)
    assert validate(result)['valid']
    for w,g in validate_groups(cfg,products_from_load_ports(cfg.load_ports)).items():
        pair=next(p for p in result['pairs'] if w in p['members'])
        cycles=[c for c in result['cycles'] if pair['id'] in c['pairs']]
        assert len(cycles)==(2 if mode=='2x2' else 1)
        assert all(abs(c['end']-c['start']-cfg.processing_groups[g][mode])<1e-6 for c in cycles)


def test_bad_duration_is_rejected_by_independent_replay():
    result=construct(config());result['cycles'][0]['end']+=1
    audit=validate(result)
    assert not audit['valid'] and any('Exposure duration' in e for e in audit['errors'])


def test_mixed_time_groups_are_rejected_even_when_durations_match():
    cfg=config(n=2)
    cfg.processing_groups={'G1':{'wafers':['LP1_W1','LP1_W2'],'4x1':80,'2x2':80}}
    result=construct(cfg)
    result['config']['processing_groups']={'G1':{'wafers':['LP1_W1'],'4x1':80,'2x2':80},
                                          'G2':{'wafers':['LP1_W2'],'4x1':80,'2x2':80}}
    assert any('Processing-group compatibility' in e for e in validate(result)['errors'])


@pytest.mark.parametrize('mutation',['missing','duplicate','unknown','negative','nan','boolean'])
def test_invalid_group_input_fails(mutation):
    cfg=config()
    if mutation=='missing':cfg.processing_groups.pop('G3')
    elif mutation=='duplicate':cfg.processing_groups['G3']['wafers']=['LP1_W1']
    elif mutation=='unknown':cfg.processing_groups['G3']['wafers']=['LP9_W1']
    else:cfg.processing_groups['G3']['4x1']={'negative':-1,'nan':float('nan'),'boolean':True}[mutation]
    with pytest.raises(ValueError):validate_groups(cfg,products_from_load_ports(cfg.load_ports))


def test_requested_configuration_is_balanced_and_exactly_100():
    cfg=configuration();products=products_from_load_ports(cfg.load_ports)
    mapping=validate_groups(cfg,products)
    assert len(mapping)==100
    assert [len(g['wafers']) for g in cfg.processing_groups.values()]==[34,33,33]
    assert [sum(v.values()) for v in cfg.load_ports.values()]==[25]*4
    assert sum(w.mode=='4x1' for w in products)==50
    assert [sum(mapping[w.identifier]==g and w.mode=='4x1' for w in products) for g in cfg.processing_groups]==[17,17,16]


def test_solver_forbids_mixing_groups_in_same_pair_or_cycle():
    cfg=config(n=2);products=products_from_load_ports(cfg.load_ports)
    for groups,expected in [(cfg.processing_groups,'infeasible'),({},'optimal')]:
        m=scip.Model();m.hideOutput()
        try:
            pair=add_joint_pairing(m,products,('D1','D2','D3','D4'),(1,),
                                  {k:(1,) for k in ('4x1','2x2','clean')},allow_cross_lp=True,max_pairs=2)
            add_chamber_cycles(m,pair,(1,),cycle_limit=1,cleaning_interval=3,
                               durations={'4x1':180,'2x2':90,'clean':500},horizon=1000,processing_groups=groups)
            m.setRealParam('limits/time',2);m.optimize()
            assert str(m.getStatus())==expected
        finally:m.freeProb()


def test_complete_event_model_accepts_group_duration_without_freezing_it_in_main_search():
    cfg=config(n=1);x=Integrated(cfg);m=x.model;m.hideOutput()
    try:
        initial=construct(cfg);fixed=constrain_seed(x,initial)
        m.setObjective(0,'minimize');m.setRealParam('limits/time',3);m.optimize()
        assert m.getNSols()>0
        sol=m.getBestSol();assert m.checkSol(sol,original=True,completely=True,printreason=False)
        result=x.result(sol);assert validate(result)['valid']
        assert result['cycles'][0]['end']-result['cycles'][0]['start']==pytest.approx(80)
        m.freeTransform()
        for v,lb,ub in fixed:m.chgVarLb(v,lb);m.chgVarUb(v,ub)
        assert all(v.getLbOriginal()==lb and v.getUbOriginal()==ub for v,lb,ub in fixed)
    finally:m.freeProb()


def test_old_default_durations_still_work():
    cfg=config(n=1);cfg.processing_groups={}
    data=construct(cfg)
    assert data['cycles'][0]['end']-data['cycles'][0]['start']==180
    assert validate(data)['valid']


def test_existing_experiments_block_launch_before_any_attempt(tmp_path,monkeypatch):
    import experiment as e
    monkeypatch.setattr(e,'configuration',lambda: config(n=1))
    out=tmp_path/'blocked';e.prepare(out)
    monkeypatch.setattr(e,'other_jobs',lambda:[{'pid':123,'script':'existing_research.py'}])
    with pytest.raises(RuntimeError,match='Existing research jobs'):e.run(out,500,1,False)
    assert not list(out.glob('attempt_*'))


def test_real_tiny_worker_checkpoint_resume_and_corruption_rejection(tmp_path,monkeypatch):
    import experiment as e
    monkeypatch.setattr(e,'configuration',lambda: config(n=1))
    out=tmp_path/'tiny';e.prepare(out)
    first=out/'attempt_001';first.mkdir();e.worker(out,first,500,0.3,None)
    pointer=e.read(first/'latest.json')
    assert e.read(first/pointer['result'])['original_model_check']
    second=out/'attempt_002';second.mkdir();e.worker(out,second,500,0.3,first)
    assert e.read(second/'result.json')['validation']['valid']
    assert (second/'model.lp.gz').exists()
    (first/pointer['variables']).write_text('{}',encoding='utf-8')
    third=out/'attempt_003';third.mkdir()
    with pytest.raises(ValueError,match='Checkpoint hash changed'):e.worker(out,third,500,0.3,first)
