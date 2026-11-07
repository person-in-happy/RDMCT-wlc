import copy
import pytest
from model4_feasible_orders import make_blocks, compose, unrank_plan
from audit_model4_reuse import project


@pytest.fixture(scope='module')
def witness():
    return compose(make_blocks()['4x1'], unrank_plan(8, 0), 3)


def test_canonical_projection_preserves_times_and_removes_solver_claims(witness):
    changed = copy.deepcopy(witness)
    swap = {'LP1_W1': 'LP1_W2', 'LP1_W2': 'LP1_W1'}
    for job in changed['jobs']:
        job['identity'] = swap.get(job['identity'], job['identity'])
    for pair in changed['pairs']:
        pair['members'] = [swap.get(w, w) for w in pair['members']]
    changed.update(solve_seconds=300, primal_dual_integral=123, status='optimal')
    qualification = {j['identity']: [2, 3] for j in changed['jobs'] if j['product']}
    decoded, report = project(changed, qualification)
    assert report['identity_map']['LP1_W2'] == 'LP1_W1'
    assert decoded['events'] == witness['events']
    assert decoded['jobs'] == witness['jobs']
    assert report['physical']['valid'] and report['pjob_count'] == 1
    assert report['nonempty_task_lp_groups'] == 4
    assert all(k not in decoded for k in ('solve_seconds', 'primal_dual_integral', 'status'))


def test_qualification_is_input_and_cannot_be_repaired_by_relabeling(witness):
    qualification = {j['identity']: [2, 3] for j in witness['jobs'] if j['product']}
    qualification['LP1_W1'] = [3]
    with pytest.raises(ValueError, match='eligibility violated'):
        project(witness, qualification)
    del qualification['LP1_W1']
    with pytest.raises(ValueError, match='exactly the frozen product inventory'):
        project(witness, qualification)


def test_distinct_qualifications_create_distinct_pjobs(witness):
    qualification = {j['identity']: [2] if j['origin']=='LP1' else [3] if j['origin']=='LP2' else [2,3]
        for j in witness['jobs'] if j['product']}
    decoded, report = project(witness, qualification)
    assert report['pjob_count'] == 3 and report['nonempty_task_lp_groups'] == 4
    assert sorted(tuple(t['chambers']) for t in decoded['pjobs']) == [(2,), (2,3), (3,)]
