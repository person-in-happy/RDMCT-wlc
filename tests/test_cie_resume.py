import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

torch = pytest.importorskip('torch')

from algorithms import HRLReinforceAlg, ReinforceBaselineAlg
from parallel_reinforce_algorithm import _find_matching_training_resume


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CIE_CODE = PROJECT_ROOT / 'cie' / 'code'
import sys

if str(CIE_CODE) not in sys.path:
    sys.path.insert(0, str(CIE_CODE))

import tune_cie_acs


class _DummyEnv:
    cutsel_use_structure_rerank = False


class _DummyPolicy(torch.nn.Linear):
    def __init__(self, feature_dim):
        super().__init__(feature_dim, 2)
        self.embedding_dim = feature_dim


def _algorithm(hierarchical=False):
    policy = _DummyPolicy(13)
    common = dict(
        sel_cuts_percent=0.2,
        device=torch.device('cpu'),
        num_epochs=60,
        baseline_type='simple',
        lr_decay=True,
        lr_decay_step=10,
        normalize=False,
    )
    if hierarchical:
        return HRLReinforceAlg(
            _DummyEnv(),
            policy,
            None,
            _DummyPolicy(13),
            train_highlevel_policy_freq=2,
            train_highlevel_batch_size=4,
            highlevel_actor_lr=5e-4,
            **common,
        )
    return ReinforceBaselineAlg(_DummyEnv(), policy, None, **common)


def test_hierarchical_checkpoint_restores_complete_training_state():
    original = _algorithm(hierarchical=True)
    original.critic_exp_mvg_avg = torch.tensor([3.25])
    original.critic_exp_mvg_avg_high_level = torch.tensor([4.5])
    original.train_highlevel_epoch = 9
    checkpoint = original._checkpoint_state_dict(epoch=17)

    restored = _algorithm(hierarchical=True)
    missing = restored.restore_training_state(checkpoint)

    assert missing == []
    assert checkpoint['training_state_version'] == 1
    assert checkpoint['epoch'] == 17
    assert restored.critic_exp_mvg_avg.item() == pytest.approx(3.25)
    assert restored.critic_exp_mvg_avg_high_level.item() == pytest.approx(4.5)
    assert restored.train_highlevel_epoch == 9


def _resume_payload(root):
    return {
        'experiment': {
            'seed': 2,
            'exp_prefix': 'cie_feature_only_all_cie_feature_only',
            'base_log_dir': str(root),
        },
        'parser_args': {
            'seed': 2,
            'scip_seed': 2,
            'reward_type': 'primaldualintegral',
            'baseline_type': 'simple',
            'policy_type': 'with_token',
            'use_cutsel_percent_policy': 'True',
        },
        'env': {'instance_file_path': 'train'},
        'algorithm': {'num_epochs': 60},
        'trainer': {'n_jobs': 2},
        'net_share': {'embedding_dim': 23},
        'policy': {'beam_size': 3},
        'value': {},
        'cutsel_percent_policy': {'use_cutsel_percent_policy': True},
        'devices': {'global_device': 'cuda:0'},
        'policy_type': 'with_token',
    }


def test_training_resume_requires_exact_identity_and_full_state(tmp_path):
    payload = _resume_payload(tmp_path)
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    (run_dir / 'variant.json').write_text(
        json.dumps(payload), encoding='utf-8'
    )
    torch.save(
        {'epoch': 23, 'training_state_version': 1}, run_dir / 'params.pkl'
    )
    torch.save(
        {'epoch': 25, 'training_state_version': 1}, run_dir / 'itr_25.pkl'
    )
    current = copy.deepcopy(payload)
    current.pop('parser_args')
    args = SimpleNamespace(**payload['parser_args'])

    resume = _find_matching_training_resume(current, args)

    assert resume['epoch'] == 25
    assert Path(resume['checkpoint']) == run_dir / 'itr_25.pkl'
    args.scip_seed = 3
    assert _find_matching_training_resume(current, args) is None


def test_unsigned_legacy_checkpoint_is_never_auto_resumed(tmp_path):
    variant = _resume_payload(tmp_path)
    run_dir = tmp_path / 'legacy_complete'
    run_dir.mkdir()
    (run_dir / 'variant.json').write_text(
        json.dumps(variant), encoding='utf-8'
    )
    torch.save({'epoch': 60}, run_dir / 'params.pkl')
    current = copy.deepcopy(variant)
    current.pop('parser_args')
    current['training_resume_signature'] = 'new-signed-protocol'
    args = SimpleNamespace(**variant['parser_args'])

    with pytest.warns(RuntimeWarning, match='pre-signature checkpoint'):
        assert _find_matching_training_resume(current, args) is None

    torch.save({'epoch': 23}, run_dir / 'params.pkl')
    with pytest.warns(RuntimeWarning, match='pre-signature checkpoint'):
        assert _find_matching_training_resume(current, args) is None


def test_acs_tuning_reuses_every_completed_evaluation(tmp_path, monkeypatch):
    instance_path = tmp_path / 'validation.lp'
    instance_path.write_text('Minimize\n obj: x\nEnd\n', encoding='utf-8')
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text('{}', encoding='utf-8')
    output_dir = tmp_path / 'acs'
    cli = SimpleNamespace(
        manifest=str(manifest_path),
        output_dir=str(output_dir),
        seeds='1',
        time_limit=1.0,
        grid_step=1.0,
        max_instances=0,
        memory_limit_mb=512.0,
        node_limit=-1,
        no_resume=False,
    )
    instance = {
        'path': str(instance_path),
        'suite': 'validation',
        'split': 'validation',
    }
    calls = []

    monkeypatch.setattr(tune_cie_acs, '_parse_args', lambda: cli)
    monkeypatch.setattr(
        tune_cie_acs,
        '_discover_instances',
        lambda *args, **kwargs: (None, [instance], []),
    )

    def fake_run(method, instance, seed, args, bundles, weights, predictions):
        calls.append((method, seed, weights))
        return {
            'path': instance['path'],
            'method': method,
            'seed': seed,
            'primal_dual_integral': 1.0,
            'gap': 0.0,
            'solving_time': 0.1,
            'error': '',
        }

    monkeypatch.setattr(tune_cie_acs, '_run_one', fake_run)
    tune_cie_acs.main()
    first_count = len(calls)
    tune_cie_acs.main()

    assert first_count == 5
    assert len(calls) == first_count
    assert len(list((output_dir / '.checkpoints').glob('*.jsonl'))) == 1
    assert len(list(output_dir.glob('acs_grid_*.json'))) == 1


def test_powershell_entrypoints_enable_resume_and_clean_interrupts():
    runner = (PROJECT_ROOT / 'cie' / 'run_cie.ps1').read_text(encoding='utf-8')
    launcher = (PROJECT_ROOT / 'cie' / 'run_cie_single.ps1').read_text(
        encoding='utf-8'
    )

    assert '--auto_resume' in runner
    assert 'function Stop-CieProcessTree' in launcher
    assert 'Stop-CieProcessTree -RootProcessId $process.Id' in launcher
    assert 'finally {' in launcher
