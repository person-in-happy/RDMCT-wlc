import copy
from collections import Counter
import pytest
from model4_feasible_orders import (family_count, unrank_plan, check_plan, make_blocks,
    compose, audit, check_pjobs, handling, render_fragments, render_plan)


@pytest.fixture(scope='module')
def blocks():
    return make_blocks()


def test_family_unranking_exhaustive_small():
    plans = [tuple(unrank_plan(4, rank)) for rank in range(family_count(4))]
    assert family_count(4) == 96
    assert len(set(plans)) == 96
    assert family_count(8) == 40320
    for plan in plans:
        check_plan(4, plan)


@pytest.mark.parametrize('recipe', ['4x1', '2x2'])
def test_composition_and_projection(blocks, recipe):
    plan = [(1, 2), (3, 3), (2, 3), (4, 2)]
    data = compose(blocks[recipe], plan, 3)
    assert audit(data)['pjob']['valid']
    assert handling(data) == render_plan(plan, render_fragments(blocks[recipe]))
    for chamber in (2, 3):
        cycles = [c for c in data['cycles'] if c['chamber'] == chamber]
        assert cycles[-1]['counter'] == 0


def test_rejects_wrong_eligibility_and_inventory(blocks):
    with pytest.raises(ValueError, match='eligibility'):
        check_plan(4, [(1, 3), (2, 3), (3, 2), (4, 3)])
    data = compose(blocks['4x1'], unrank_plan(4, 0), 3)
    product = next(j for j in data['jobs'] if j['product'] and j['origin'] == 'LP1')
    data['pairs'][product['pair']]['chamber'] = 3
    with pytest.raises(ValueError, match='chamber'):
        check_pjobs(data)
    with pytest.raises(ValueError, match='inventory'):
        check_plan(4, [(1, 2)] * 4)


def test_identity_swaps_do_not_create_anonymous_sequences(blocks):
    data = compose(blocks['4x1'], unrank_plan(8, 0), 3)
    changed = copy.deepcopy(data)
    mapping = {'LP1_W1': 'LP1_W2', 'LP1_W2': 'LP1_W1'}
    for p in changed['pairs']:
        p['members'] = [mapping.get(w, w) for w in p['members']]
    for j in changed['jobs']:
        j['name'] = mapping.get(j['name'], j['name'])
        j['identity'] = mapping.get(j['identity'], j['identity'])
    for e in changed['events']:
        if e.get('job') in mapping:
            e['job'] = mapping[e['job']]
            e['name'] = e['job'] + '_' + e['kind']
    assert handling(data, anonymous=True) == handling(changed, anonymous=True)
    assert handling(data) != handling(changed)
    with pytest.raises(ValueError, match='Noncanonical'):
        check_pjobs(changed)


def test_real_source_or_chamber_choices_remain_distinct(blocks):
    a = [(1, 2), (2, 3), (3, 2), (4, 2)]
    b = [(1, 2), (2, 3), (3, 3), (4, 2)]
    c = [(2, 3), (1, 2), (3, 2), (4, 2)]
    assert len({handling(compose(blocks['4x1'], plan, 3), anonymous=True) for plan in (a,b,c)}) == 3
