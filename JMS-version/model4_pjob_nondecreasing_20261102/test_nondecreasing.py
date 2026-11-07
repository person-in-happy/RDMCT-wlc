"""Bounded correctness tests only; never launch a formal campaign."""
from pathlib import Path
from dataclasses import replace
import copy
import sys
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'JMS-version/experiments/nondecreasing_followup_20261102'))
import followup_models as fm
from model import Config, Integrated
from seed import construct, constrain_seed
from pjob_order import order_report
from validate import validate


def config(n=2, same_lp=True, recipe='4x1'):
    ports={f'LP{i}': {'4x1':0, '2x2':0} for i in range(1,5)}
    for i in range(n): ports[f'LP{1 if same_lp else i%4+1}'][recipe]+=1
    return Config(ports, cleaning_interval=3)


def limits(m):
    m.hideOutput()
    m.setIntParam('parallel/maxnthreads',1)
    m.setRealParam('limits/time',20)
    m.setRealParam('limits/memory',1024)
    m.setObjective(0)


@pytest.mark.parametrize('same_lp',[True,False])
def test_order_checker_allows_equality_but_rejects_reversal(same_lp):
    data=construct(config(same_lp=same_lp))
    assert validate(data)['valid']
    picks=[e for e in data['events'] if e['kind']=='origin_pick' and e['job'].startswith('prod')]
    picks[1]['start']=picks[0]['start']
    assert order_report(data)['valid']
    picks[1]['start']=picks[0]['start']-1
    assert not order_report(data)['valid']


@pytest.mark.parametrize('recipe',['4x1','2x2'])
@pytest.mark.parametrize('arm',['pjob','wafer'])
def test_full_model_accepts_same_task_same_pair_sync(recipe,arm):
    x=fm.build_fair(config(recipe=recipe),arm); m=x.model
    try:
        # Fix a known physical structure, leaving all timings/sync choices free.
        # This tests feasibility of the changed rule, not global search speed.
        constrain_seed(x,construct(x.cfg),times=False)
        g=x.groups[0]
        m.addCons(x.pair.member[g.identifier,0,0]==1)
        m.addCons(x.pair.member[g.identifier,0,1]==1)
        m.addCons(x.jobs['prod_0_0']['first']['s']==x.jobs['prod_0_1']['first']['s'])
        if arm=='wafer':
            # Exercise the valid equal-time identity permutation explicitly.
            labels=sorted(fm.encoding(x.cfg),key=lambda w:fm.encoding(x.cfg)[w]['pjob_index'])
            m.addCons(m.wafer_selectors[labels[1],0,0]==1)
            m.addCons(m.wafer_selectors[labels[0],0,1]==1)
        limits(m);m.setIntParam('limits/solutions',1);m.optimize()
        assert m.getNSols()>0, 'No feasible witness: '+str(m.getStatus())
        sol=m.getBestSol()
        assert m.checkSol(sol,original=True,completely=True)
        data=x.result(solution=sol)
        check=validate(data)
        assert check['valid'], check['errors']
        fm.assert_wafer_decode(x,sol,data)
        picks=sorted(e['start'] for e in data['events'] if e['kind']=='origin_pick' and e['job'].startswith('prod'))
        assert abs(picks[0]-picks[1])<1e-5
        assert data['release_order_rule']=='global_pjob_index_nondecreasing_lp_pickup'
    finally:m.freeProb()


@pytest.mark.parametrize('violation',['reverse_lp','sync_across_lp','sync_different_pairs'])
def test_physical_conflicts_still_infeasible(violation):
    x=Integrated(config(same_lp=violation=='sync_different_pairs'));m=x.model
    try:
        g=x.groups[0]; h=x.groups[-1]
        p=1 if violation=='sync_different_pairs' else 0
        r=0 if p==1 else 1
        m.addCons(x.pair.member[g.identifier,0,0]==1)
        m.addCons(x.pair.member[h.identifier,p,r]==1)
        a=x.jobs['prod_0_0']['first'];b=x.jobs[f'prod_{p}_{r}']['first']
        if violation=='reverse_lp':m.addCons(b['s']<=a['s']-1)
        else:m.addCons(b['s']==a['s'])
        limits(m);m.optimize()
        assert str(m.getStatus())=='infeasible',str(m.getStatus())
    finally:m.freeProb()


def test_wafer_time_reversal_rejected_by_original_constraints():
    x=fm.build_fair(config(),'wafer');m=x.model
    try:
        labels=sorted(fm.encoding(x.cfg),key=lambda w:fm.encoding(x.cfg)[w]['pjob_index'])
        m.addCons(x.wafer_pickup[labels[1]]<=x.wafer_pickup[labels[0]]-1)
        limits(m);m.optimize()
        assert str(m.getStatus())=='infeasible'
    finally:m.freeProb()
