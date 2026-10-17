"""Structural tests: these do not certify a full equipment schedule."""
import pytest
pytest.importorskip('pyscipopt')
from scip_imports import scip
from joint_pairing_model import ProductWafer, add_joint_pairing


def make(products, *, cross=True, dummies=(), slots=2):
    m=scip.Model();m.hideOutput()
    x=add_joint_pairing(m,products,dummies,(2,3),{'4x1':(2,3),'2x2':(2,3)},
                        allow_cross_lp=cross,max_pairs=slots)
    return m,x


@pytest.mark.parametrize('second_chamber',[2,3])
def test_pairing_and_chambers_are_not_fixed(second_chamber):
    ps=[ProductWafer(f'W{i}',i,'2x2') for i in range(1,5)]
    m,x=make(ps)
    # Nonconsecutive cross-LP partners and both balanced/unbalanced allocation.
    for w,p,r in [('W1',0,0),('W3',0,1),('W2',1,0),('W4',1,1)]:
        m.addCons(x.member[w,p,r]==1)
    m.addCons(x.chamber[0,2]==1);m.addCons(x.chamber[1,second_chamber]==1)
    m.optimize();assert str(m.getStatus())=='optimal'
    assert all(v.vtype()=='BINARY' for group in vars(x).values() for v in group.values())


def test_different_product_recipes_cannot_share_pair():
    m,x=make([ProductWafer('A',1,'4x1'),ProductWafer('B',2,'2x2')],slots=1)
    m.optimize();assert str(m.getStatus())=='infeasible'


def test_cross_lp_restriction_is_explicit():
    m,x=make([ProductWafer('A',1,'2x2'),ProductWafer('B',2,'2x2')],cross=False,slots=1)
    m.optimize();assert str(m.getStatus())=='infeasible'


def test_dummy_can_be_reused_in_distinct_pair_demands():
    m,x=make([ProductWafer('A',1,'4x1'),ProductWafer('B',4,'2x2')],dummies=('D1',))
    m.optimize();assert str(m.getStatus())=='optimal'
    assert sum(m.getVal(v) for v in x.dummy_identity.values())==pytest.approx(2)


def test_one_physical_dummy_cannot_fill_two_sides_of_one_pair():
    m,x=make([],dummies=('D1',),slots=1);m.addCons(x.active[0]==1)
    m.optimize();assert str(m.getStatus())=='infeasible'


def test_two_dummies_can_form_support_pair():
    m,x=make([],dummies=('D1','D2'),slots=1);m.addCons(x.active[0]==1)
    m.optimize();assert str(m.getStatus())=='optimal'


def test_lp_mode_counts_are_explicit_input():
    from joint_pairing_model import products_from_load_ports
    ps=products_from_load_ports({'LP1':{'4x1':2,'2x2':1},'LP2':{'2x2':3},'LP3':{},'LP4':{'4x1':1}})
    assert len(ps)==7
    assert len({w.identifier for w in ps})==7
    assert sum(w.mode=='4x1' for w in ps)==3
    assert [w.load_port for w in ps]==[1,1,1,2,2,2,4]


@pytest.mark.parametrize('target',[(2,0),(3,1)])
def test_position_is_a_binary_choice(target):
    from joint_pairing_model import add_pair_positions
    m,d=make([ProductWafer('A',1,'2x2'),ProductWafer('B',4,'2x2')],slots=1)
    x=add_pair_positions(m,d,[('2x2',c,k) for c in (2,3) for k in (0,1)])
    m.addCons(x[0,'2x2',*target]==1);m.optimize()
    assert str(m.getStatus())=='optimal'
    assert m.getVal(d.chamber[0,target[0]])==pytest.approx(1)


@pytest.mark.parametrize('second_start,expected',[(5,'infeasible'),(10,'optimal')])
def test_physical_dummy_reuse_requires_disjoint_complete_intervals(second_start,expected):
    from joint_pairing_model import add_dummy_reuse_timing
    m,d=make([ProductWafer('A',1,'4x1'),ProductWafer('B',4,'2x2')],dummies=('D1',))
    for w,p in [('A',0),('B',1)]:m.addCons(d.member[w,p,0]==1)
    starts={};ends={}
    for p,r in d.dummy:
        starts[p,r]=m.addVar(lb=0,ub=30);ends[p,r]=m.addVar(lb=0,ub=30)
        begin=0 if p==0 else second_start
        m.addCons(starts[p,r]==(begin if r==1 else 0))
        m.addCons(ends[p,r]==(begin+10 if r==1 else 0))
    add_dummy_reuse_timing(m,d,starts,ends,horizon=30)
    m.optimize();assert str(m.getStatus())==expected
