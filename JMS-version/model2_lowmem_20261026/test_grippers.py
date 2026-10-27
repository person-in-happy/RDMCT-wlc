"""Regression tests for physical clean/dirty hand eligibility and occupancy."""
import copy
from dataclasses import replace
import pytest
from model import Config, Integrated
from seed import construct, constrain_seed
from validate import validate
from grippers import HANDS, assign_intervals, attach_hands

def test_two_dirty_two_clean_can_overlap():
    intervals=[('raw1',0,10,HANDS[:2]),('raw2',1,11,HANDS[:2]),('done1',2,12,HANDS[2:]),('done2',3,13,HANDS[2:])]
    assert assign_intervals(intervals) is not None

def test_three_unprocessed_products_rejected_below_total_capacity():
    assert assign_intervals([(str(i),i,10,HANDS[:2]) for i in range(3)]) is None

def test_auxiliary_choice_requires_lookahead_and_is_not_greedy():
    x=assign_intervals([('aux1',0,10,HANDS),('aux2',1,11,HANDS),('raw1',2,12,HANDS[:2]),('raw2',3,13,HANDS[:2])])
    assert x is not None and {x['aux1'],x['aux2']}==set(HANDS[2:])

def test_immediate_reuse_and_no_mid_transport_switch():
    assert assign_intervals([('a',0,5,('D1',)),('b',5,10,('D1',))]) is not None
    # At every time some hand is free, but no single hand is free throughout x.
    assert assign_intervals([('a',0,5,('D1',)),('x',1,9,('D1','D2')),('b',5,10,('D2',))]) is None

def config():
    return Config({'LP1':{'4x1':1},'LP2':{},'LP3':{},'LP4':{}},dummy_count=4,max_pairs=2,max_cycles=1,chambers=(1,))

def test_validator_rejects_wrong_product_hand_and_missing_assignment():
    d=construct(config());j=next(j for j in d['jobs'] if j['product'])
    assert j['vtr_hand_in'].startswith('D') and j['vtr_hand_out'].startswith('C')
    j['vtr_hand_in']='C1';assert not validate(d)['valid']
    del j['vtr_hand_in'];assert not validate(d)['valid']

def test_validator_rejects_shared_physical_hand_for_overlapping_members():
    d=construct(config());members=[j for j in d['jobs'] if j['pair']==0]
    assert len(members)==2
    for j in members:j['vtr_hand_in']='D1'
    assert any('VTR hand D1 capacity' in e for e in validate(d)['errors'])

def test_legacy_is_explicit_and_retagging_without_hands_fails():
    d=construct(replace(config(),vtr_hand_policy='legacy_unrestricted'))
    del d['config']['vtr_hand_policy'];assert validate(d)['valid']
    d['config']['vtr_hand_policy']='clean_dirty';assert not validate(d)['valid']
    assert attach_hands(d) and validate(d)['valid']

@pytest.mark.parametrize('leg,wrong',[('in',2),('out',0)])
def test_milp_forbids_wrong_product_hand(leg,wrong):
    x=Integrated(config());m=x.model
    m.addCons(x.vtr_hands['LP1_W1_'+leg,wrong]==1)
    m.setRealParam('limits/time',5);m.optimize()
    assert str(m.getStatus())=='infeasible';m.freeProb()

def test_original_milp_exports_complete_hand_witness():
    x=Integrated(config());m=x.model;constrain_seed(x,construct(x.cfg));m.setObjective(0)
    m.setRealParam('limits/time',15);m.optimize();assert m.getNSols()>0
    d=x.result();assert validate(d)['valid']
    assert all(j['vtr_hand_in'] in HANDS and j['vtr_hand_out'] in HANDS for j in d['jobs'])
    m.freeProb()

