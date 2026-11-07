import copy,json
from dataclasses import replace,asdict
import pytest
from model import Config,Integrated
from pjobs import groups_from_config,with_qualification_profile
from seed import construct,constrain_seed,release_fixed,normalize_schedule
from validate import validate
from joint_pairing_model import add_pjob_pairing
from reference_completion import complete_reference
from scip_imports import scip


def config(n=1,mode='4x1',source='dual',same_lp=False,h=3):
    ports={f'LP{i}':{'4x1':0,'2x2':0} for i in range(1,5)}
    for i in range(n):ports[f'LP{1 if same_lp else i%4+1}'][mode]+=1
    return Config(ports,source=source,cleaning_interval=h)


def test_group_inventory_and_invalid_qualification():
    cfg=with_qualification_profile(config(8),'three_classes')
    groups=groups_from_config(cfg)
    assert len({g.pjob for g in groups})==3 and sum(g.count for g in groups)==8
    bad=copy.deepcopy(cfg.pjobs);bad[0]['wafers'].append(bad[0]['wafers'][0])
    with pytest.raises(ValueError):replace(cfg,pjobs=bad)
    bad=copy.deepcopy(cfg.pjobs);bad[0]['chambers']=[]
    with pytest.raises(ValueError):replace(cfg,pjobs=bad)


@pytest.mark.parametrize('compatible',[True,False])
def test_cross_pjob_pairing_depends_on_intersection(compatible):
    cfg=config(2)
    tasks=[dict(id='Pjob1',mode='4x1',chambers=[2],wafers=['LP1_W1']),
           dict(id='Pjob2',mode='4x1',chambers=[2,3] if compatible else [3],wafers=['LP2_W1'])]
    cfg=replace(cfg,pjobs=tasks);groups=groups_from_config(cfg);m=scip.Model();m.hideOutput()
    p=add_pjob_pairing(m,groups,('D1','D2','D3','D4'),cfg.chambers,2,2)
    m.addCons(p.member[groups[0].identifier,0,0]==1);m.addCons(p.member[groups[1].identifier,0,1]==1)
    m.setRealParam('limits/time',5);m.optimize()
    assert (m.getNSols()>0)==compatible
    if not compatible:assert str(m.getStatus())=='infeasible'
    m.freeProb()


@pytest.mark.parametrize('source',['single','dual'])
@pytest.mark.parametrize('mode',['4x1','2x2'])
def test_full_model_reference_and_decoding(source,mode):
    cfg=config(mode=mode,source=source,h=2)
    schedule=construct(cfg);assert validate(schedule)['valid']
    x=Integrated(cfg)
    assert not any('_W' in v.name for v in x.model.getVars())
    assert len(x.pair.member)==2*len(x.groups)*min(x.N,x.P)
    serial,common,levels,cert=complete_reference(x,schedule,1024,0)
    sol=x.model.createSol()
    for v in x.model.getVars():x.model.setSolVal(sol,v,common[v.name])
    assert x.model.checkSol(sol,original=True,completely=True)
    result=x.result(sol);assert validate(result)['valid']
    assert abs(result['cmax']-schedule['cmax'])<1e-5
    assert next(j for j in result['jobs'] if j['product'])['wafer_number']==1
    x.model.freeSol(sol);x.model.freeProb()


def test_qualified_mixed_tasks_full_model():
    cfg=with_qualification_profile(config(3),'three_classes')
    data=construct(cfg,balanced=True);assert validate(data)['valid']
    x=Integrated(cfg);_,values,_,_=complete_reference(x,data,2048,0)
    sol=x.model.createSol()
    for v in x.model.getVars():x.model.setSolVal(sol,v,values[v.name])
    assert x.model.checkSol(sol,original=True,completely=True)
    assert validate(x.result(sol))['valid']
    x.model.freeSol(sol);x.model.freeProb()
    changed=copy.deepcopy(data);changed['config']['pjobs'][0]['chambers']=[3]
    assert not validate(changed)['valid']


def test_product_permutation_collapses_but_source_remains():
    cfg=config(2,same_lp=True);data=construct(cfg)
    changed=copy.deepcopy(data);swap={'LP1_W1':'LP1_W2','LP1_W2':'LP1_W1'}
    for p in changed['pairs']:p['members']=[swap.get(w,w) for w in p['members']]
    for j in changed['jobs']:j['identity']=swap.get(j['identity'],j['identity'])
    normalized=normalize_schedule(cfg,changed)
    assert [j['identity'] for j in normalized['jobs']]==[j['identity'] for j in data['jobs']]
    assert validate(normalized)['valid']


@pytest.mark.parametrize('balanced,h',[(False,3),(True,10)])
def test_product_only_reference_without_cleaning_candidates(balanced,h):
    # Full 4x1 loads need neither support pairs nor a cleaning before H.
    # The active completion model therefore has constant-zero clean kinds,
    # including both the first-cycle and successor-cycle boundary cases.
    cfg=config(8,h=h);data=construct(cfg,balanced=balanced)
    assert all(p['mode']=='4x1' and all(not w.startswith('D') for w in p['members'])
               for p in data['pairs'])
    assert max(p['id'] for p in data['pairs'])+1<sum(g.count for g in groups_from_config(cfg))
    x=Integrated(cfg)
    try:
        _,values,_,cert=complete_reference(x,data,2048,0)
        assert cert['active_pairs']<x.N
        sol=x.model.createSol()
        try:
            for v in x.model.getVars():x.model.setSolVal(sol,v,values[v.name])
            assert x.model.checkSol(sol,original=True,completely=True)
            result=x.result(sol)
            assert validate(result)['valid'] and abs(result['cmax']-data['cmax'])<1e-5
        finally:x.model.freeSol(sol)
    finally:x.model.freeProb()


def test_solver_and_refinement_pipeline(tmp_path):
    from run_experiments import solve
    cfg=config();path=tmp_path/'config.json';path.write_text(json.dumps(asdict(cfg)))
    summary=solve(path,tmp_path/'run',time_limit=3,stage2_limit=2,memory_mb=1024,initialization='serial',method='scip')
    result=json.loads((tmp_path/'run/result.json').read_text())
    assert summary['valid'] and result['original_model_check']
    assert result['model_scope']=='model4_pjob_inventory_v1'
    assert result['validation']['pjob_check'] and result['full_candidate_space']


def test_campaign_matrices_and_frozen_policy_metadata():
    from evidence_supplement import matrix,defaults
    from joint_algorithms import policy_record
    expected={'core':126,'ablation':216,'crossover':216,'sensitivity':96,'doe':180,'ood':81,'rhythm':48,'cleaning':96,'fixed':12,'gantt16':4,'diagnostic':4}
    for suite,count in expected.items():
        cases,pairs=matrix(suite)
        assert len(pairs)*len(defaults(suite)['seeds'])==count
        assert all(Config(**c).pjobs for c in cases.values())
    for method in ('hem','proposed','feature_only','proposed_greedy','proposed_no_structure'):
        assert policy_record(method)['sha256']


def test_mixed_recipe_single_source_qualified_full_completion():
    ports={f'LP{i}':{'4x1':int(i<=2),'2x2':int(i>2)} for i in range(1,5)}
    cfg=with_qualification_profile(Config(ports,source='single',cleaning_interval=3),'three_classes')
    data=construct(cfg,balanced=True);assert validate(data)['valid']
    assert {p['mode'] for p in data['pairs']}=={'4x1','2x2','clean'}
    x=Integrated(cfg);_,values,_,_=complete_reference(x,data,2048,0)
    sol=x.model.createSol()
    for v in x.model.getVars():x.model.setSolVal(sol,v,values[v.name])
    assert x.model.checkSol(sol,original=True,completely=True) and validate(x.result(sol))['valid']
    x.model.freeSol(sol);x.model.freeProb()


def test_flexible_task_can_split_across_chambers():
    cfg=config(2,same_lp=True);groups=groups_from_config(cfg);m=scip.Model();m.hideOutput()
    p=add_pjob_pairing(m,groups,('D1','D2','D3','D4'),cfg.chambers,2,2)
    for pair,c in enumerate(cfg.chambers):
        m.addCons(p.member[groups[0].identifier,pair,0]==1);m.addCons(p.chamber[pair,c]==1)
    m.optimize();assert m.getNSols()>0;m.freeProb()


def test_campaign_worker_audit_cold_serial_fixed_and_refined(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import evidence_supplement as e
    import revalidate as r
    # A tiny CPU-only controller fixture; these cells are not paper evidence.
    key='controller_fixture';cfg=asdict(config());arms=('joint','cold','serial','fixed','refined')
    monkeypatch.setattr(e,'matrix',lambda suite:({key:cfg},[(key,arm) for arm in arms]))
    monkeypatch.setattr(e,'campaign_path',lambda value:__import__('pathlib').Path(value).resolve())
    out=tmp_path/'controller'
    args=SimpleNamespace(campaign=str(out),suite='smoke',memory_mb=1024,process_memory_mb=1536,jobs=1,time_limit=2,
                         wall_limit=120,spbs_budget=0,seeds=[1],qualification='all',cut_profile='root_only')
    e.prepare(args);spec=json.loads((out/'campaign.json').read_text())
    r.prepare_reference(out,key,spec)
    for cell in spec['cells']:r.worker(out,cell['id'])
    report=e.audit(out)
    assert report['coverage_complete'] and len(report['rows'])==len(arms)


@pytest.mark.parametrize('mode',['4x1','2x2'])
def test_tiny_search_witnesses_map_to_both_full_models(tmp_path,mode):
    import subprocess,sys
    from pathlib import Path
    from run_experiments import solve
    root=Path(__file__).resolve().parents[2]
    cfg=config(mode=mode);path=tmp_path/'model4.json';path.write_text(json.dumps(asdict(cfg)))
    solve(path,tmp_path/'new',time_limit=2,stage2_limit=0,memory_mb=1024,initialization='serial',method='scip')
    oldcfg=asdict(cfg);oldcfg.pop('pjobs');oldpath=tmp_path/'model2.json';oldpath.write_text(json.dumps(oldcfg))
    command=[sys.executable,'-X','utf8',str(root/'JMS-version/model2_lowmem_20261026/run_experiments.py'),'solve',
        '--config',str(oldpath),'--output',str(tmp_path/'old'),'--time-limit','2','--stage2-limit','0',
        '--memory-mb','1024','--initialization','serial']
    done=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=90)
    assert done.returncode==0,done.stdout[-3000:]+done.stderr[-3000:]
    a=json.loads((tmp_path/'new/result.json').read_text());b=json.loads((tmp_path/'old/result.json').read_text())
    assert a['validation']['valid'] and b['validation']['valid']
    # A fixed budget need not prove either optimum. Test both physical
    # mappings against the complete MILPs instead of asserting solver speed.
    x=Integrated(cfg);projected=normalize_schedule(cfg,b)
    _,values,_,_=complete_reference(x,projected,1024,0)
    sol=x.model.createSol()
    for v in x.model.getVars():x.model.setSolVal(sol,v,values[v.name])
    assert x.model.checkSol(sol,original=True,completely=True)
    assert abs(x.result(sol)['cmax']-b['cmax'])<2e-4
    x.model.freeSol(sol);x.model.freeProb()
    from projection import to_model2
    converted=tmp_path/'preimage.json';converted.write_text(json.dumps(to_model2(a)))
    script="""import sys,json
sys.path.insert(0,sys.argv[1])
from model import Config,Integrated
from reference_completion import complete_reference
data=json.load(open(sys.argv[2])); x=Integrated(Config(**data['config']))
_,values,_,_=complete_reference(x,data,1024,0)
sol=x.model.createSol()
for v in x.model.getVars():x.model.setSolVal(sol,v,values[v.name])
assert x.model.checkSol(sol,original=True,completely=True)
assert abs(x.result(sol)['cmax']-data['cmax'])<2e-4
x.model.freeSol(sol);x.model.freeProb()
"""
    done=subprocess.run([sys.executable,'-c',script,str(root/'JMS-version/model2_lowmem_20261026'),str(converted)],
                        cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=90)
    assert done.returncode==0,done.stdout[-3000:]+done.stderr[-3000:]
    assert a['primary_bound']<=b['cmax']+2e-4 and b['primary_bound']<=a['cmax']+2e-4
    if a['primary_status']==b['primary_status']=='optimal':assert abs(a['cmax']-b['cmax'])<2e-4
