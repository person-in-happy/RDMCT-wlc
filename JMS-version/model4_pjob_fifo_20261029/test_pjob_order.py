import copy
from dataclasses import replace
import pytest
from model import Integrated
from test_model4 import config
from seed import construct
from pjob_order import encoding, order_report
from scip_imports import scip


def test_noncontinuous_ids_have_contiguous_batch_indices():
    cfg = config(3)
    codes = encoding(cfg)
    assert [(v['pjob_index'], v['wafer_number']) for v in codes.values()] == [(1,1),(2,26),(3,51)]


@pytest.mark.parametrize('same_lp', [False, True])
def test_global_release_checker_rejects_wrong_order_and_equal_starts(same_lp):
    cfg = config(2, same_lp=same_lp)
    data = construct(cfg)
    assert order_report(data)['valid']
    changed = copy.deepcopy(data)
    picks = [e for e in changed['events'] if e['kind']=='origin_pick' and e['job'].startswith('prod')]
    assert len(picks)==2
    picks[1]['start'] = picks[0]['start']
    assert not order_report(changed)['valid']
    picks[1]['start'] = picks[0]['start']-10
    assert not order_report(changed)['valid']


@pytest.mark.parametrize('violation', ['reversed_lp', 'simultaneous_same_task'])
def test_complete_model_proves_forced_release_violation_infeasible(violation):
    cfg = config(2, same_lp=violation=='simultaneous_same_task')
    x = Integrated(cfg)
    m = x.model
    try:
        if violation=='reversed_lp':
            g,h=x.groups
            m.addCons(x.pair.member[g.identifier,0,0]==1)
            m.addCons(x.pair.member[h.identifier,1,0]==1)
            left=x.jobs['prod_0_0']['first'];right=x.jobs['prod_1_0']['first']
            m.addCons(right['s']<=left['s'])
        else:
            g=x.groups[0]
            m.addCons(x.pair.member[g.identifier,0,0]==1)
            m.addCons(x.pair.member[g.identifier,0,1]==1)
            m.addCons(x.jobs['prod_0_0']['first']['s']==x.jobs['prod_0_1']['first']['s'])
        m.setRealParam('limits/time',5);m.setRealParam('limits/memory',512)
        m.optimize()
        assert str(m.getStatus())=='infeasible'
    finally:m.freeProb()


def test_cross_task_sync_rule_does_not_forbid_joint_pickup():
    # Isolate the added rule: two qualified tasks may use one simultaneous pair.
    from types import SimpleNamespace
    from pjobs import groups_from_config
    from joint_pairing_model import add_pjob_pairing
    from pjob_order import restrict_pick_sync
    cfg=config(2,same_lp=True)
    cfg=replace(cfg,pjobs=[dict(id='Pjob1',mode='4x1',chambers=[2],wafers=['LP1_W1']),
                          dict(id='Pjob2',mode='4x1',chambers=[2,3],wafers=['LP1_W2'])])
    m=scip.Model();m.hideOutput();groups=groups_from_config(cfg)
    pair=add_pjob_pairing(m,groups,('D1','D2','D3','D4'),cfg.chambers,2,2)
    x=SimpleNamespace(model=m,groups=groups,pair=pair,
                      jobs={'a':{'product':(0,0)},'b':{'product':(0,1)}})
    sync=m.addVar(vtype='B')
    restrict_pick_sync(x,dict(kind='origin_pick',job='a'),dict(kind='origin_pick',job='b'),sync)
    m.addCons(pair.member[groups[0].identifier,0,0]==1)
    m.addCons(pair.member[groups[1].identifier,0,1]==1)
    m.addCons(sync==1);m.optimize()
    assert m.getNSols()>0
    m.freeProb()


@pytest.mark.parametrize('n',[4,8,16])
def test_balanced_seed_preserves_batch_order_across_chambers(n):
    data=construct(config(n),balanced=True)
    assert order_report(data)['valid']
    assert len({p['chamber'] for p in data['pairs']})==2


def test_strict_release_requires_positive_pickup_duration():
    with pytest.raises(ValueError,match='atr_handling must be positive'):
        Integrated(replace(config(),atr_handling=0))


def test_focused_paper_matrices_have_no_duplicate_cells():
    from evidence_supplement import matrix,defaults
    for suite,total in [('paper',102),('rhythm',48),('qualification',6),('paper_cuts',72)]:
        cases,pairs=matrix(suite)
        assert len(pairs)==len(set(pairs))
        assert len(pairs)*len(defaults(suite)['seeds'])==total
        assert all(key in cases for key,arm in pairs)
