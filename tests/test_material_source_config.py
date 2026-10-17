import pytest
from material_source_config import MaterialSourceConfig

@pytest.mark.parametrize('lp',[1,2,3,4])
def test_single_source_dummy_bypasses_alignment(lp):
    cfg=MaterialSourceConfig(False)
    route=cfg.dummy_route(1,load_port=lp)
    assert route[:3]==(f'LP{lp}','ATR','LLupper')
    assert 'AL' not in route
    assert cfg.product_route(lp,1)[1:5]==('ATR','AL','ATR','LLupper')

def test_accompanying_dummy_is_held_by_atr():
    route=MaterialSourceConfig(False).dummy_route(2,atmospheric_storage='AS beside LP4',accompany_product=True)
    assert route[2]=='AL vicinity (held on ATR)'
    assert 'AL' not in route
    assert route[-1]=='AS beside LP4'

def test_dual_source_dummy_stays_in_vacuum():
    assert MaterialSourceConfig(True).dummy_route(2,vacuum_storage='VS1')==('VS1','VTR','CH2','VTR','VS1')

@pytest.mark.parametrize('kwargs',[{}, {'vacuum_storage':'VS1'}, {'load_port':1,'atmospheric_storage':'AS'}])
def test_reject_wrong_single_origin(kwargs):
    with pytest.raises(ValueError):MaterialSourceConfig(False).dummy_route(1,**kwargs)

def test_reject_dual_source_al_visit():
    with pytest.raises(ValueError):MaterialSourceConfig(True).dummy_route(1,vacuum_storage='VS',accompany_product=True)
