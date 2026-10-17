"""Checks of actual released pairing/chamber decisions and baseline feasibility."""
import copy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model import Config,Integrated
from seed import construct,constrain_seed
from supplement_protocol import balanced_reference
from validate import validate

@pytest.mark.parametrize('source',['single','dual'])
@pytest.mark.parametrize('n',[6,8,16,24])
def test_two_chamber_reference(source,n):
    from run_experiments import ports
    cfg=Config(ports(n,'mixed'),source=source,cleaning_interval=3)
    r=balanced_reference(cfg)
    assert validate(r)['valid']
    assert {p['chamber'] for p in r['pairs']}==set(cfg.chambers)

@pytest.mark.parametrize('cross',[False,True])
@pytest.mark.parametrize('chamber',[1,2])
def test_distinct_memberships_and_chambers_have_physical_witnesses(cross,chamber):
    cfg=Config({'LP1':{'4x1':2},'LP2':{'4x1':2},'LP3':{},'LP4':{}},cleaning_interval=3)
    original=construct(cfg);template=copy.deepcopy(original)
    if cross:
        template['pairs'][0]['members']=['LP1_W1','LP2_W1']
        template['pairs'][1]['members']=['LP1_W2','LP2_W2']
    for p in template['pairs']:p['chamber']=chamber
    for c in template['cycles']:c['chamber']=chamber
    r=construct(cfg,template);assert validate(r)['valid']
    x=Integrated(cfg);fixed=constrain_seed(x,r);m=x.model;m.setObjective(0,'minimize');m.setRealParam('limits/time',10);m.optimize()
    assert m.getNSols()>0
    assert validate(x.result())['valid']
    values={v.name:m.getSolVal(m.getBestSol(),v) for v in m.getVars(transformed=False)}
    m.freeTransform()
    for v,lb,ub in fixed:m.chgVarLb(v,lb);m.chgVarUb(v,ub)
    sol=m.createSol()
    for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
    assert m.checkSol(sol,printreason=False,completely=True)
    m.freeSol(sol);m.freeProb()
