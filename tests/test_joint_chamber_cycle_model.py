import pytest
pytest.importorskip('pyscipopt')
from scip_imports import scip
from joint_pairing_model import ProductWafer,add_joint_pairing
from joint_chamber_cycle_model import add_chamber_cycles


def make(mode,H,Q,P):
    m=scip.Model();m.hideOutput();m.setParam('limits/time',15)
    d=add_joint_pairing(m,[ProductWafer('A',1,mode),ProductWafer('B',4,mode)],
        ('D1','D2','D3','D4'),(2,3),{x:(2,3) for x in ('4x1','2x2','clean')},
        allow_cross_lp=True,max_pairs=P)
    m.addCons(d.member['A',0,0]==1);m.addCons(d.member['B',0,1]==1)
    m.addCons(d.chamber[0,3]==1)
    cy=add_chamber_cycles(m,d,(2,3),cycle_limit=Q,cleaning_interval=H,
                         durations={'4x1':6,'2x2':3,'clean':5},horizon=100)
    m.setObjective(scip.quicksum(cy.used.values()),'minimize')
    return m,d,cy


def test_chain_has_two_adjacent_exposures_and_dummy_ends():
    m,d,c=make('2x2',3,3,3);m.optimize();assert m.getNSols()>0
    assert sum(m.getVal(v) for (p,ch,q),v in c.occupancy.items() if p==0)==pytest.approx(2)
    assert sum(m.getVal(v) for (ch,q,k),v in c.kind.items() if k=='2x2')==pytest.approx(2)
    assert sum(m.getVal(v) for (ch,q,k),v in c.kind.items() if k=='clean')==pytest.approx(0)


def test_cleaning_is_triggered_by_actual_cycles():
    m,d,c=make('2x2',2,3,5);m.optimize();assert m.getNSols()>0
    assert sum(m.getVal(v) for (ch,q,k),v in c.kind.items() if k=='clean')==pytest.approx(1)


def test_four_by_one_has_one_exposure():
    m,d,c=make('4x1',3,2,2);m.optimize();assert m.getNSols()>0
    assert sum(m.getVal(v) for (p,ch,q),v in c.occupancy.items() if p==0)==pytest.approx(1)


def test_two_exposures_cannot_be_cut_by_cleaning_at_H1():
    m,d,c=make('2x2',1,4,7);m.optimize();assert str(m.getStatus())=='infeasible'


def solve_sequence(sequence, H):
    """Fix physical occupancy; only test the cleaning state machine."""
    m=scip.Model();m.hideOutput();m.setParam('limits/time',10)
    products=[ProductWafer(f'W{q}',1,'4x1') for q,k in enumerate(sequence) if k=='4x1']
    d=add_joint_pairing(m,products,('D1','D2','D3','D4'),(2,),
        {k:(2,) for k in ('4x1','2x2','clean')},allow_cross_lp=True,max_pairs=2*len(sequence))
    c=add_chamber_cycles(m,d,(2,),cycle_limit=len(sequence),cleaning_interval=H,
        durations={'4x1':6,'2x2':3,'clean':5},horizon=100)
    for q,k in enumerate(sequence):
        m.addCons(c.kind[2,q,k]==1)
        m.addCons(c.occupancy[2*q,2,q]==1)
        m.addCons(c.occupancy[2*q+1,2,q]==1)
        if k=='4x1':m.addCons(d.member[f'W{q}',2*q,0]==1)
    m.optimize()
    return m,c


@pytest.mark.parametrize('count',[1,2,3,4,5])
def test_cleaning_allowed_after_any_positive_count(count):
    m,c=solve_sequence(['4x1']*count+['clean'],5)
    assert m.getNSols()>0,str(m.getStatus())
    assert m.getVal(c.counter[2,count])==pytest.approx(0)


def test_early_cleaning_can_precede_four_by_one_and_repeat_after_production():
    m,c=solve_sequence(['4x1','clean','4x1','clean'],10)
    assert m.getNSols()>0,str(m.getStatus())
    assert [m.getVal(c.counter[2,q]) for q in range(4)]==pytest.approx([1,0,1,0])


@pytest.mark.parametrize('sequence',[
    ['clean','4x1'],
    ['4x1','clean','clean'],
    ['4x1','4x1','4x1'],
    ['4x1','4x1','4x1','4x1','clean'],
])
def test_cleaning_still_rejects_empty_or_overdue_sequences(sequence):
    m,_=solve_sequence(sequence,3)
    assert str(m.getStatus())=='infeasible'


def test_early_cleaning_cannot_split_two_exposures():
    m,d,c=make('2x2',5,3,5)
    m.addCons(c.kind[3,1,'clean']==1)
    m.optimize()
    assert str(m.getStatus())=='infeasible'
