"""Regression: short handling times expose nonadjacent ATR travel constraints."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import Config
from revalidate import plan, prepare
from supplement_protocol import balanced_reference
from validate import validate


@pytest.mark.parametrize('n', [4, 8])
def test_fast_single_source_respects_nonadjacent_ll_return(n):
    cases, _ = plan('sensitivity')
    cfg = Config(**cases[f'n{n}_H3_mixed_single_transport0.8'])
    result = balanced_reference(cfg)
    assert validate(result)['valid']
    # Check the previously failing ordered pair directly, independently of
    # the constructor's travel bookkeeping.
    events = result['events']
    count = 0
    for earlier in events:
        if earlier['robot'] != 'ATR' or earlier['kind'] != 'lower_pick':
            continue
        for later in events:
            if (later['robot'] == 'ATR' and later['kind'] == 'origin_pick'
                    and later['start'] >= earlier['end']):
                assert later['start'] >= earlier['end'] + cfg.atr_empty_ll_to_lp - 1e-6
                count += 1
    assert count


def test_prepare_subset_freezes_six_cells(tmp_path):
    selected = ['n4_H3_mixed_single_transport0.8', 'n8_H3_mixed_single_transport0.8']
    out = tmp_path/'subset'
    prepare(SimpleNamespace(suite='sensitivity', cases=selected, output=str(out),
                            seeds=[1, 2, 3], training_seed=1, time_limit=300,
                            spbs_budget=20, cut_profile='standard', memory_mb=6000,
                            wall_limit=1800))
    spec = json.loads((out/'campaign.json').read_text())
    assert spec['selected_cases'] == selected
    assert len(spec['cells']) == 6
    assert set(spec['case_hashes']) == set(selected)
    assert {c['seed'] for c in spec['cells']} == {1, 2, 3}
    assert all(c['variant'] == 'joint' for c in spec['cells'])


def test_unknown_subset_does_not_leave_partial_directory(tmp_path):
    out = tmp_path/'invalid'
    with pytest.raises(ValueError, match='Unknown cases'):
        prepare(SimpleNamespace(suite='sensitivity', cases=['typo'], output=str(out)))
    assert not out.exists()
