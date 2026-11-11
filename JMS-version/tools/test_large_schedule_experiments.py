"""Scientific acceptance gates: restricted or secondary optima cannot be promoted."""
import json
from types import SimpleNamespace
import pytest
import large_schedule_experiments as exp


def fixture_result():
    cfg=exp.configuration(SimpleNamespace(size=100,recipe='mixed',cleaning_interval=3,dummy_count=8))
    return dict(config=exp.asdict(cfg),solutions=1,original_model_check=True,validation=dict(valid=True),
                full_candidate_space=True,restricted_candidate_bounds=False,experiment_scope='joint',
                primary_objective='product_return_cmax',primary_status='optimal',
                primary_bound=9000.,cmax=9000.,primary_gap=0.,
                jobs=[dict(product=True) for _ in range(100)],
                cycles=[dict(mode=mode) for mode in ('4x1','2x2','clean')])


def test_full_target_can_be_certified():
    assert exp.proof_verdict(fixture_result())['target_global_optimal']


@pytest.mark.parametrize('change',[
    dict(primary_status='timelimit'),dict(primary_bound=8900.),
    dict(primary_gap=.1),dict(primary_bound=float('inf')),
    dict(full_candidate_space=False),dict(restricted_candidate_bounds=True),
    dict(experiment_scope='fixed_configuration'),dict(phase='secondary'),
    dict(primary_objective='waiting'),dict(original_model_check=False),
    dict(validation=dict(valid=False))])
def test_reject_false_global_claim(change):
    data=fixture_result();data.update(change)
    assert not exp.proof_verdict(data)['target_global_optimal']


def test_reject_candidate_limit_even_if_flag_claims_full():
    data=fixture_result();data['config']['max_pairs']=180
    assert not exp.proof_verdict(data)['full_primary_optimal']


def test_auxiliary_jobs_do_not_count_as_products():
    data=fixture_result();data['jobs'][-1]['product']=False
    assert not exp.proof_verdict(data)['target_100_mixed_clean']


@pytest.mark.parametrize('omitted',['4x1','2x2','clean'])
def test_require_actual_modes_and_cleaning(omitted):
    data=fixture_result();data['cycles']=[c for c in data['cycles'] if c['mode']!=omitted]
    assert not exp.proof_verdict(data)['target_global_optimal']


def test_n100_inventory_and_unrestricted_bounds():
    cfg=exp.Config(**fixture_result()['config']);bounds=exp.capacity(cfg)
    assert bounds['mode_counts']=={'4x1':50,'2x2':50}
    assert all(sum(p.values())==25 for p in cfg.load_ports.values())
    assert bounds['full_candidate_pairs']==550
    assert bounds['full_candidate_cycles_per_chamber']==300
    assert bounds['necessary_minimum_cleaning_cycles']==12
    assert cfg.max_pairs==cfg.max_cycles==0


def test_cross_campaign_certificate_is_rejected(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(exp,'checked',lambda out: {})
    (tmp_path/'campaign.json').write_text('{}')
    dest=tmp_path/'solve';dest.mkdir()
    (dest/'resources.json').write_text('{}')
    (dest/'certificate.json').write_text(json.dumps(dict(campaign_sha256='another-run')))
    with pytest.raises(RuntimeError,match='different campaign'):
        exp.status(tmp_path)


def test_strict_status_never_counts_an_unproved_final_result_as_success(tmp_path,monkeypatch):
    monkeypatch.setattr(exp,'checked',lambda out:dict(settings=dict(until_optimal=True)))
    (tmp_path/'campaign.json').write_text('{}')
    dest=tmp_path/'solve';dest.mkdir()
    (dest/'resources.json').write_text('{}')
    data=fixture_result();data['primary_status']='userinterrupt'
    exp.dump(dest/'result.json',data)
    exp.dump(dest/'certificate.json',dict(status='userinterrupt',cmax=9000,primary_bound=0,
        campaign_sha256=exp.digest(tmp_path/'campaign.json'),result_sha256=exp.digest(dest/'result.json'),
        verdict=exp.proof_verdict(data)))
    assert exp.status(tmp_path)['complete']==0
    assert exp.status(tmp_path)['failed']==1


def test_strict_mode_resets_termination_caps_without_memory_quota():
    model=exp.scip.Model()
    try:
        memory=model.getParam('limits/memory')
        model.setRealParam('limits/time',1.)
        model.setLongintParam('limits/nodes',1)
        model.setIntParam('limits/solutions',1)
        model.setRealParam('limits/gap',.5)
        exp.configure_stopping(model,dict(until_optimal=True))
        assert model.getParam('limits/time')>=1e19
        assert model.getParam('limits/nodes')==-1
        assert model.getParam('limits/solutions')==-1
        assert model.getParam('limits/gap')==model.getParam('limits/absgap')==0
        assert model.getParam('limits/memory')==memory
    finally:
        model.freeProb()


def mock_schedule(model,objective):
    """Tiny SCIP model tests publication mechanics, not schedule feasibility."""
    def result(solution):
        data=fixture_result()
        data['cmax']=model.getSolVal(solution,objective)
        return data
    return SimpleNamespace(model=model,cmax=objective,result=result)


def test_incumbents_commit_improve_resume_and_reject_invalid(tmp_path,monkeypatch):
    monkeypatch.setattr(exp,'validate',lambda data:dict(valid=True))
    (tmp_path/'campaign.json').write_text('{}')
    model=exp.scip.Model()
    try:
        v=model.addVar('objective',lb=0,ub=20,obj=1)
        x=mock_schedule(model,v)
        publisher=exp.IncumbentPublisher(x,tmp_path)
        def solution(value):
            sol=model.createSol();model.setSolVal(sol,v,value);return sol
        first=solution(10)
        path=publisher.publish(first)
        assert exp.read(path/'variables.json')['values']['objective']==10
        assert not exp.read(tmp_path/'latest_incumbent.json')['certified_global_optimal']
        assert publisher.publish(first) is None
        model.freeSol(first)
        second=solution(8);publisher.publish(second);model.freeSol(second)
        pointer=(tmp_path/'latest_incumbent.json').read_bytes()
        monkeypatch.setattr(exp,'validate',lambda data:dict(valid=False,errors=['bad route']))
        rejected=solution(6)
        with pytest.raises(RuntimeError,match='physical replay'):
            publisher.publish(rejected)
        model.freeSol(rejected)
        assert (tmp_path/'latest_incumbent.json').read_bytes()==pointer
        resumed=exp.IncumbentPublisher(x,tmp_path)
        assert resumed.best==8 and resumed.count==2
        worse=solution(9)
        assert resumed.publish(worse) is None
        with pytest.raises(RuntimeError,match='worse'):
            resumed.publish(worse,final=True)
        model.freeSol(worse)
        # A partial write must not reuse the same immutable directory on retry.
        (tmp_path/'incumbents'/'000003').mkdir()
        resumed=exp.IncumbentPublisher(x,tmp_path)
        assert resumed.count==3 and resumed.best==8
    finally:
        model.freeProb()


def test_real_scip_callback_and_final_proof_label(tmp_path,monkeypatch):
    monkeypatch.setattr(exp,'validate',lambda data:dict(valid=True))
    (tmp_path/'campaign.json').write_text('{}')
    model=exp.scip.Model()
    try:
        model.hideOutput()
        v=model.addVar('objective',vtype='I',lb=0,ub=20,obj=1)
        model.addCons(v>=3)
        publisher=exp.IncumbentPublisher(mock_schedule(model,v),tmp_path)
        model.includeEventhdlr(exp.PublishBestSolution(publisher),'test_publish','test')
        model.optimize()
        assert not (tmp_path/'incumbent_export_error.json').exists()
        assert publisher.count>=1
        assert not exp.read(tmp_path/'latest_incumbent.json')['certified_global_optimal']
        publisher.publish(model.getBestSol(),final=True)
        pointer=exp.read(tmp_path/'latest_incumbent.json')
        assert pointer['cmax']==3 and pointer['certified_global_optimal']
    finally:
        model.freeProb()


def test_live_render_needs_no_final_solve_and_updates_same_paths(tmp_path,monkeypatch):
    import sys
    monkeypatch.setattr(exp,'checked',lambda out:{})
    monkeypatch.setattr(exp,'validate',lambda data:dict(valid=True))
    (tmp_path/'campaign.json').write_text('{}')
    exp.dump(tmp_path/'config.json',fixture_result()['config'])
    drawn=[]
    def draw(data,output,optimal):
        output.mkdir(parents=True,exist_ok=True)
        (output/'gantt_resources.png').write_text(str(data['cmax'])+':'+str(optimal))
        drawn.append(data['cmax'])
    monkeypatch.setitem(sys.modules,'large_schedule_plot',SimpleNamespace(draw=draw))
    def snapshot(number,cmax,optimal=False):
        dest=tmp_path/'incumbents'/str(number);dest.mkdir(parents=True)
        d=fixture_result();d.update(cmax=cmax,primary_bound=cmax,
                                  primary_status='optimal' if optimal else 'solving')
        exp.dump(dest/'result.json',d)
        exp.dump(dest/'variables.json',dict(values={}))
        exp.dump(dest/'certificate.json',dict(
            campaign_sha256=exp.digest(tmp_path/'campaign.json'),
            result_sha256=exp.digest(dest/'result.json'),
            variables_sha256=exp.digest(dest/'variables.json')))
        exp.dump(tmp_path/'latest_incumbent.json',dict(snapshot=dest.relative_to(tmp_path).as_posix()))
        return dest
    old=snapshot(1,9000)
    exp.render(tmp_path)
    target=tmp_path/'figures'/'gantt_resources.png'
    assert target.read_text()=='9000:False'
    with pytest.raises(ValueError,match='unproved'):
        exp.render(tmp_path,require_optimal=True)
    snapshot(2,8900);exp.render(tmp_path)
    assert target.read_text()=='8900:False'
    snapshot(3,8900,True);exp.render(tmp_path,require_optimal=True)
    assert target.read_text()=='8900:True'
    exp.render(tmp_path,snapshot=old)
    assert target.read_text()=='8900:True'
    assert drawn==[9000,8900,8900]
