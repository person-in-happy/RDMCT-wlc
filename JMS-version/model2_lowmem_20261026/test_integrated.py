"""Physical integration tests, including adversarial changes to exported schedules."""
from pathlib import Path
import sys,copy,json
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model import Config,Integrated
from validate import validate
from seed import construct,constrain_seed

def cfg(mode='4x1',source='dual',h=3,n=1,p=2,q=1):
    return Config({'LP1':{mode:n},'LP2':{},'LP3':{},'LP4':{}},source=source,cleaning_interval=h,max_pairs=p,max_cycles=q,chambers=(2,),dummy_count=4)

def run(c,layout):
    x=Integrated(c);m=x.model
    schedule=construct(c);constrain_seed(x,schedule)
    m.setObjective(0,'minimize');m.setRealParam('limits/time',20);m.optimize()
    assert m.getNSols()>0,str(m.getStatus())
    result=x.result();v=validate(result);assert v['valid'],v['errors']
    return x,result

@pytest.fixture(scope='module')
def reference():
    _,r=run(cfg(),[(0,'4x1','LP1_W1',[0],[0]),(1,'4x1',None,[0],[])])
    return r

def test_full_route_and_grippers(reference):
    assert validate(reference)['valid']


@pytest.mark.parametrize('source',['single','dual'])
def test_optional_cleaning_full_physics_and_candidate_capacity(source):
    # Two separate productive cycles, each followed by cleaning at count 1 < H.
    # The old floor(T/(H-1)) bound would forbid both cleanings at H=10.
    c=cfg(source=source,h=10,n=2,p=0,q=0)
    template={'pairs':[], 'cycles':[]}
    for q,mode in enumerate(('4x1','clean','4x1','clean')):
        members=[f'LP1_W{q//2+1}','D1'] if mode=='4x1' else ['D3','D4']
        template['pairs'].extend([
            dict(id=2*q,members=members,mode=mode,chamber=2),
            dict(id=2*q+1,members=['D2','D3'] if mode=='4x1' else ['D1','D2'],mode=mode,chamber=2)])
        template['cycles'].append(dict(chamber=2,index=q,mode=mode,pairs=[2*q,2*q+1],front=2*q+1))
    schedule=construct(c,template)
    assert schedule['validation']['valid']
    x=Integrated(c)
    assert x.safe_bounds=={'pairs':8,'cycles_per_chamber':4}
    assert not x.bounded
    constrain_seed(x,schedule)
    x.model.setObjective(0,'minimize');x.model.setRealParam('limits/time',20);x.model.optimize()
    assert x.model.getNSols()>0,str(x.model.getStatus())
    result=x.result()
    assert result['cleaning_policy']=='optional_before_threshold'
    assert validate(result)['valid']
    assert [v['counter'] for v in result['cycles']]==pytest.approx([1,0,1,0])


def test_validator_rejects_missing_terminal_cleaning():
    r=construct(cfg('2x2',h=3,p=3,q=2))
    r['config']['cleaning_interval']=2
    verdict=validate(r)
    assert not verdict['valid']
    assert any('Missing terminal cleaning' in error for error in verdict['errors'])

@pytest.mark.parametrize('source',['single','dual'])
def test_two_exposures_and_terminal_cleaning(source):
    # One product+dummy pair, head/tail support and two cleaning pairs.
    x,r=run(cfg('2x2',source,2,p=5,q=3),[(0,'2x2','LP1_W1',[0,1],[0]),(1,'2x2',None,[0],[]),(2,'2x2',None,[1],[1]),(3,'clean',None,[2],[]),(4,'clean',None,[2],[2])])
    assert validate(r)['cleaning_count']==1
    assert [c['mode'] for c in r['cycles']]==['2x2','2x2','clean']
    assert all(j['origin']==('AS' if source=='single' else 'VS') for j in r['jobs'] if not j['product'])

@pytest.mark.parametrize('fault',['duration','robot_overlap','origin','duplicate_dummy','orientation','missing_product','loan','cmax'])
def test_reject_corrupted_physics(reference,fault):
    r=copy.deepcopy(reference)
    if fault=='duration':r['cycles'][0]['end']-=10
    elif fault=='robot_overlap':
        a,b=[e for e in r['events'] if e['robot']=='ATR'][:2];b['start']=a['start'];b['end']=a['end']
    elif fault=='origin':next(j for j in r['jobs'] if not j['product'])['origin']='AS'
    elif fault=='duplicate_dummy':r['pairs'][1]['members'][1]=r['pairs'][1]['members'][0]
    elif fault=='orientation':r['cycles'][0]['front']=1-r['cycles'][0]['front']
    elif fault=='missing_product':r['jobs']=[j for j in r['jobs'] if not j['product']]
    elif fault=='loan':r['jobs'][0]['loan_end']-=1
    elif fault=='cmax':r['cmax']=1
    if fault=='missing_product':
        # Missing required material must fail closed, not crash during maxima.
        assert not validate(r)['valid']
    else:assert not validate(r)['valid']

@pytest.mark.parametrize('n',[2,4,6,8,16,24])
@pytest.mark.parametrize('source',['single','dual'])
@pytest.mark.parametrize('mode',['4x1','2x2','mixed'])
def test_multiscale_physical_construction(n,source,mode):
    from run_experiments import ports
    for h in (2,3,10):
        r=construct(Config(ports(n,mode),source=source,cleaning_interval=h))
        assert r['validation']['valid']

def test_ll_reset_does_not_block_vtr_travel(reference):
    cfg=reference['config'];pick=next(e for e in reference['events'] if e['kind']=='source_pick' and e['job']=='LP1_W1')
    load=next(e for e in reference['events'] if e['kind']=='pair_load' and e['pair']==next(j['pair'] for j in reference['jobs'] if j['product']))
    assert pick['end']<=load['start']<pick['end']+cfg['upper_reset']

def test_three_wafers_cannot_be_held_by_atr():
    x=Integrated(cfg(n=3));m=x.model
    picks=[e for e in x.events if e['kind']=='origin_pick' and e.get('job','').startswith('LP')]
    puts=[e for e in x.events if e['kind']=='al_put' and e.get('job','').startswith('LP')]
    for i,a in enumerate(picks):m.addCons(a['s']==i*x.cfg.atr_handling)
    for e in x.robots['ATR']:
        if e not in picks:m.addCons(e['s']>=3*x.cfg.atr_handling*e['active'])
    m.setRealParam('limits/time',10);m.optimize()
    assert str(m.getStatus())=='infeasible'

@pytest.mark.parametrize('source',['single','dual'])
@pytest.mark.parametrize('mode',['4x1','2x2'])
def test_retime_template_preserves_structure(source,mode):
    c=Config({'LP1':{mode:3},'LP2':{mode:3},'LP3':{},'LP4':{}},source=source,cleaning_interval=3)
    original=construct(c)
    # A structure template can be used even when the old event timestamps are invalid.
    original['events'][0]['end']+=100
    regenerated=construct(c,original)
    assert regenerated['validation']['valid']
    assert regenerated['pairs']==original['pairs']
    assert [(v['mode'],v['pairs'],v['front']) for v in regenerated['cycles']]==[(v['mode'],v['pairs'],v['front']) for v in original['cycles']]


def test_single_source_dummy_has_no_alignment_events():
    c=cfg(source='single')
    data=construct(c)
    ds={j['name'] for j in data['jobs'] if not j['product']}
    assert not any(e.get('job') in ds and e['location']=='AL' for e in data['events'])
    assert validate(data)['valid']
    # Relabeling a legacy all-aligned schedule cannot validate the new route.
    legacy=construct(Config(**{**data['config'],'dummy_alignment':'legacy_align_all'}))
    legacy['config']['dummy_alignment']='bypass_or_accompany'
    assert not validate(legacy)['valid']


def test_single_source_accompanied_entry_and_early_drop_rejected():
    from run_experiments import fix_structure
    c=cfg(source='single');x=Integrated(c);m=x.model
    reference=construct(c);fix_structure(x,reference)
    escort=x.escorts['aux_0_1','LP1_W1'];m.addCons(escort==1)
    # This checks accompaniment feasibility and rejection of an early drop;
    # optimizing Cmax only adds unrelated search variability to the time cap.
    m.setObjective(0,'minimize')
    m.setRealParam('limits/time',15);m.optimize()
    assert m.getNSols()>0,str(m.getStatus())
    data=x.result();check=validate(data);assert check['valid'],check['errors']
    events={(e.get('job'),e['kind']):e for e in data['events']}
    dp=events['aux_0_1','origin_pick'];pa=events['LP1_W1','al_put']
    du=events['aux_0_1','upper_put'];pu=events['LP1_W1','upper_put']
    assert dp['end']<=pa['start']+1e-4
    assert abs(du['start']-pu['start'])<1e-4 and abs(du['end']-pu['end'])<1e-4
    broken=copy.deepcopy(data)
    wrong=next(e for e in broken['events'] if e.get('job')=='aux_0_1' and e['kind']=='upper_put')
    wrong['start']-=5;wrong['end']-=5
    assert not validate(broken)['valid']
