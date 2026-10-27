"""Projection tests for the actual color-disjunction constraints."""
import itertools
from types import SimpleNamespace
import pytest
from model import Integrated,scip


def test_conditional_robot_prefix_projection_exhaustive():
    # Enumerate all binary orientations, including cyclic ones: the identity
    # holds independently of temporal ordering or synchronization constraints.
    n=3;pairs=list(itertools.combinations(range(n),2))
    for active in itertools.product((0,1),repeat=n):
        for changes in itertools.product((-2,-1,1,2),repeat=n):
            M=sum(map(abs,changes))+4
            for order in itertools.product((0,1),repeat=len(pairs)):
                old=[changes[i]*active[i] for i in range(n)];new=old.copy()
                for (i,j),o in zip(pairs,order):
                    both=active[i]*active[j]
                    assert (o<=both)==(2*o<=active[i]+active[j])
                    if o>both:break
                    old[j]+=changes[i]*o;new[j]+=changes[i]*o
                    old[i]+=changes[j]*(both-o);new[i]+=changes[j]*(active[j]-o)
                else:
                    for i in range(n):
                        if active[i]:assert new[i]==old[i]
                        else:assert -M<=new[i]<=4+M and -M<=old[i]<=4+M


@pytest.mark.parametrize('colors',[2,4,8,10])
def test_actual_disjunction_matches_same_resource_interval_oracle(colors):
    x=Integrated.__new__(Integrated);x.model=m=scip.Model();m.hideOutput();x.M=300
    x.H=100;x.cfg=SimpleNamespace(upper_reset=30,lower_reset=25)
    data={k:m.addVar(lb=0,ub=130 if k.startswith('e') else 100,name=k) for k in ('si','ei','sj','ej')}
    data.update({k:m.addVar(vtype='B',name=k) for k in ('ai','aj')})
    data.update({k:m.addVar(vtype='I',lb=0,ub=colors,name=k) for k in ('ci','cj')})
    x.colored_nonoverlap('test', [('i',data['si'],data['ei'],data['ai']),
        ('j',data['sj'],data['ej'],data['aj'])],{'i':data['ci'],'j':data['cj']},colors)
    for ai,aj in itertools.product((0,1),repeat=2):
        for ci,cj in itertools.product(range(1,colors+1),repeat=2):
            for (si,ei),(sj,ej) in itertools.product(((0,1),(1,2),(99,100),(99,130),(0,130)),repeat=2):
                expected=not(ai and aj and ci==cj) or sj>=ei or si>=ej
                values=dict(ai=ai,aj=aj,ci=ci if ai else 0,cj=cj if aj else 0,si=si,ei=ei,sj=sj,ej=ej)
                feasible=False
                for order in (0,1):
                    sol=m.createSol()
                    for k,v in data.items():m.setSolVal(sol,v,values[k])
                    for v in m.getVars():
                        if v.name=='order_test_i_j':m.setSolVal(sol,v,order)
                    feasible |= m.checkSol(sol,printreason=False,completely=True,original=True)
                    m.freeSol(sol)
                assert feasible==expected,(colors,values)
    m.freeProb()


def test_disjoint_hand_domains_remove_only_irrelevant_pairs():
    x=Integrated.__new__(Integrated);x.model=m=scip.Model();m.hideOutput();x.M=300
    x.H=100;x.cfg=SimpleNamespace(upper_reset=30,lower_reset=25)
    x.colored_nonoverlap('test',[('i',0,2,1),('j',0,2,1)],{'i':1,'j':3},4,
        allowed={'i':(0,1),'j':(2,3)})
    assert m.getNVars()==0 and m.getNConss()==0
    m.freeProb()


@pytest.mark.parametrize('cycles',[1,2,3,4])
def test_cycle_aliases_for_every_admissible_two_chamber_occupancy(cycles):
    for bits in itertools.product((0,1),repeat=2*cycles):
        occ=[bits[:cycles],bits[cycles:]]
        first=[[o[q]*(1-o[q-1] if q else 1) for q in range(cycles)] for o in occ]
        last=[[o[q]*(1-o[q+1] if q+1<cycles else 1) for q in range(cycles)] for o in occ]
        for active,mixed in ((0,0),(1,0),(1,1)):
            if sum(bits)!=active+mixed or sum(map(sum,first))!=active:continue
            for c,o in enumerate(occ):
                for q in range(cycles):
                    next_occ=o[q+1] if q+1<cycles else 0
                    next_first=first[c][q+1] if q+1<cycles else 0
                    assert last[c][q]==o[q]-next_occ+next_first
                    assert first[c][q]*mixed==o[q]-last[c][q]
                    assert last[c][q]*mixed==o[q]-first[c][q]
                    for front in (0,1):
                        if front>first[c][q] or front<next_occ-next_first:continue
                        assert front*last[c][q]==front-(o[q]-last[c][q])
                        assert last[c][q]-front*last[c][q]==o[q]-front
