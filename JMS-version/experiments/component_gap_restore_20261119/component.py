"""Run a single component/seed cell using the frozen full-domain A and physical B solvers."""
import argparse
from pathlib import Path
from types import SimpleNamespace
import sys
import time

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / 'manuscript_certified_gaps_20261119'))
from design import OUT as PARENT, RESULTS, ROOT, read, save, sha


OUT = RESULTS / 'component_gap_restore_20261119_r1'
PHYSICAL = RESULTS / 'manuscript_certified_gaps_physicalB_20261119_r2'
# method, inference feature dimension, decoding, checkpoint postprocessor, evaluation reranking
POLICIES = {
    'full': ('proposed', 23, 'beam_search', 'role_submodular_v1', True),
    'no_rerank': ('proposed_no_structure', 23, 'beam_search', 'role_submodular_v1', False),
    'feature_only': ('feature_only', 23, 'greedy', 'none', False),
    'greedy': ('proposed_greedy', 23, 'greedy', 'role_submodular_v1', True),
    'hem_spbs': ('hem', 13, 'greedy', 'none', False),
}
TUNE_CASES = ('D_n2_4x1_scenario1', 'D_n2_mixed_scenario3')
GAP = '0p01pct'


def folders(case, method):
    if case not in TUNE_CASES or method not in POLICIES:
        raise ValueError('Unknown case or component')
    if method in ('full', 'no_rerank'):
        return (PARENT/'runs'/case/method/('A_' + GAP),
                PHYSICAL/'runs'/case/method/('B_' + GAP + '_' + GAP))
    base = OUT/'runs'/case/method
    return base/('A_' + GAP), base/('B_' + GAP + '_' + GAP)


def policy_on_cpu(model, method, spec, solver_seed, training_seed):
    """Use identical network classes/weights as the archived ablations, on a single CPU thread."""
    import numpy as np
    import torch
    from joint_algorithms import policy_record
    sys.path.insert(0, str(ROOT/'cie/code'))
    import run_cie_benchmarks as cie

    expected_method, dimension, decode, checkpoint_postprocessor, rerank = spec
    if method != expected_method:
        raise ValueError('Solver and requested component differ')
    torch.set_num_threads(1)
    torch.manual_seed(solver_seed)
    np.random.seed(solver_seed)
    record = policy_record(method, training_seed)
    cfg = read(record['config'])
    checkpoint = torch.load(record['checkpoint'], map_location='cpu', weights_only=False)
    net = cfg['net_share']
    if net['embedding_dim'] != dimension:
        raise ValueError('Feature dimension differs from historical method')
    cie.validate_checkpoint_feature_schema(checkpoint, dimension, record['checkpoint'])
    cie.validate_checkpoint_postprocessor_schema(checkpoint, dimension, record['checkpoint'], checkpoint_postprocessor)
    args = dict(embedding_dim=dimension, hidden_dim=net['hidden_dim'],
                tanh_exploration=net['tanh_exploration'], use_tanh=net['use_tanh'], use_cuda=False)
    policy = cie.PointerNetworkEndToken(**args, n_glimpses=cfg['policy']['n_glimpses'],
                                        beam_size=cfg['policy']['beam_size'])
    upper = cie.CutsPercentPolicy(**args, n_process_block_iters=cfg['value']['n_process_block_iters'])
    policy.load_state_dict(checkpoint['pointer_net'])
    upper.load_state_dict(checkpoint['cutsel_percent_net'])
    policy.eval()
    upper.eval()
    norm = None
    if 'mean' in checkpoint:
        norm = cie.RunningMeanStd((dimension,))
        norm.set_mean_std(checkpoint['mean'], checkpoint['std'])
    bundle = dict(policy=policy, high_level=upper, mean_std=norm, device='cpu')
    options = SimpleNamespace(sel_cuts_percent=.2, decode_type=decode, policy_type='with_token',
                              cutsel_max_candidates=128, cutsel_max_selected_cuts=16,
                              structure_pool_factor=2., structure_anchor_ratio=.25,
                              structure_quality_weight=.35, structure_policy_weight=.20,
                              structure_coverage_weight=.25, structure_representation_weight=.20)
    agent = cie._build_agent(SimpleNamespace(m=model), bundle, options, rerank)
    model.includeCutsel(agent, 'manuscript_cutsel', 'frozen component policy', 666666)
    record.update(feature_dimension=dimension, decode_type=decode, rerank=rerank,
                  training_postprocessor=checkpoint_postprocessor, device='cpu')
    return agent, record


def solve(phase, case, method):
    import msvcrt
    if method in ('full', 'no_rerank'):
        raise ValueError('Selected reference runs are read-only')
    pa, pb = folders(case, method)
    folder = pa if phase == 'A' else pb
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'worker.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return 73
        if (folder/'evidence.json').is_file():
            return 0
        protocol = read(OUT/'protocol.json')
        attempt = folder/'attempts'/str(time.time_ns())
        attempt.mkdir(parents=True)
        if phase == 'B':
            sys.path.insert(0, str(HERE.parent/'manuscript_fixed_rhythm_20261119'))
            import secondary
            secondary.PRIMARY = OUT
            secondary.worker(case, method, GAP, GAP, folder, attempt)
        else:
            import worker as primary
            spec = POLICIES[method]
            # Each worker is a fresh interpreter. Only the component selector is substituted.
            primary.METHODS = {method: (spec[0], True)}
            primary.install_cpu = lambda model, name: policy_on_cpu(model, name, spec, 1, 1)
            primary.solve(PARENT, protocol['cases'][case], (phase, method, GAP, GAP), folder, attempt)
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('phase', choices=['A','B'])
    ap.add_argument('case', choices=TUNE_CASES)
    ap.add_argument('method', choices=POLICIES)
    a = ap.parse_args()
    sys.exit(solve(a.phase, a.case, a.method))
