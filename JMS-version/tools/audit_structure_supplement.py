"""Replay paired, strong-start and dummy-identity checks without optimization."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'JMS-version' / 'joint_model'))
from model import Config, Integrated
from run_experiments import assets, digest, fix_structure
from validate import validate


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def signature(data):
    """Ignore event times; exact equality also rules out any relabeling claim."""
    return {
        'pairs': sorted(data['pairs'], key=lambda x: x['id']),
        'cycles': [
            {k: q[k] for k in ('chamber', 'index', 'mode', 'pairs', 'front')}
            for q in sorted(data['cycles'], key=lambda x: (x['chamber'], x['index']))
        ],
    }


def resolve_asset(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def check_assignment(config, values, reference=None):
    x = Integrated(Config(**config))
    m = x.model
    m.hideOutput()
    if reference is not None:
        fix_structure(x, reference)
    assert set(values) == {v.name for v in m.getVars()}
    sol = m.createSol()
    for v in m.getVars():
        m.setSolVal(sol, v, values[v.name])
    valid = bool(m.checkSol(sol, printreason=False, completely=True))
    m.freeSol(sol)
    m.freeProb()
    return valid


def exposure_overlaps(data):
    productive = [q for q in data['cycles'] if q['mode'] != 'clean']
    return [dict(chambers=[a['chamber'], b['chamber']],
                 cycles=[a['index'], b['index']],
                 start=max(a['start'], b['start']), end=min(a['end'], b['end']))
            for i, a in enumerate(productive) for b in productive[i+1:]
            if a['chamber'] != b['chamber']
            and min(a['end'], b['end']) > max(a['start'], b['start']) + 2e-4]


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--witness', type=Path)
    parser.add_argument('--strong-start', type=Path)
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    current_assets = assets()
    report = {'campaign': str(campaign), 'scope': 'Read-only replay; no optimization',
              'audit_tool_sha256': digest(Path(__file__)),
              'assets': current_assets, 'instances': []}
    for common in sorted(campaign.glob('common_*')):
        config = read(common / 'config.json')
        cert = read(common / 'certificate.json')
        reference = read(common / 'reference.json')
        manifest = read(common / 'manifest.json')
        assert manifest['assets'] == current_assets
        assert manifest['protocol_sha256'] == digest(ROOT / 'JMS-version/joint_model/supplement_protocol.py')
        cfg_source = campaign / 'inputs/configs' / (common.name.removeprefix('common_') + '.json')
        assert manifest['source_config_sha256'] == digest(cfg_source)
        assert read(cfg_source) == config
        warm = read(common / 'variables.json')
        assert warm['config_sha256'] == digest(common / 'config.json')
        matched = campaign / common.name.replace('common_', 'matched_', 1)
        protocol = read(matched / 'protocol.json')
        assert protocol['assets'] == current_assets
        assert protocol['warm_sha256'] == digest(common / 'variables.json')
        assert protocol['reference_sha256'] == digest(common / 'reference.json')
        assert protocol['budget'] == 1800 and protocol['seed'] == 1
        assert cert['valid'] and validate(reference)['valid']
        x = Integrated(Config(**config))
        m = x.model
        m.hideOutput()

        def check_values(values):
            assert set(values) == {v.name for v in m.getVars()}
            sol = m.createSol()
            for v in m.getVars():
                m.setSolVal(sol, v, values[v.name])
            ok = m.checkSol(sol, printreason=False, completely=True)
            m.freeSol(sol)
            return bool(ok)

        assert check_values(warm['values'])
        row = {'config': config, 'common_cmax': cert['cmax'],
               'initialization_seconds': cert['seconds'],
               'common_assignment_full_MILP_valid': True, 'runs': []}
        for method in ('scip_fixed', 'scip_joint'):
            run = matched / method
            d = read(run / 'result.json')
            mf = read(run / 'manifest.json')
            assert mf['assets'] == current_assets
            assert mf['config'] == config
            assert mf['time_limit'] == 1800 and mf['stage2_limit'] == 0 and mf['seed'] == 1
            assert mf['warm_start_sha256'] == protocol['warm_sha256']
            assert mf['lp_sha256'] == digest(run / 'model.lp.gz')
            assert bool(mf['fixed_reference']) == (method == 'scip_fixed')
            if method == 'scip_fixed':
                assert mf['fixed_reference_sha256'] == protocol['reference_sha256']
            assert read(run / 'warm_start_check.json')['accepted']
            physical = validate(d)
            assert physical['valid'], physical['errors']
            assert abs(physical['product_return_cmax'] - d['cmax']) < 2e-4
            values = read(run / 'variables.json')['values']
            assert check_values(values)
            if method == 'scip_fixed':
                assert check_assignment(config, values, reference)
            structural_prefixes = ('jp_', 'jc_used', 'jc_kind', 'jc_occ', 'jc_first',
                                   'jc_last', 'jc_product_pair', 'jc_mixed_product', 'front_')
            structural = {k: v for k, v in values.items() if k.startswith(structural_prefixes)}
            delta = [k for k, v in structural.items() if abs(v-warm['values'][k]) > 2e-4]
            pairs = {p['id']: p for p in d['pairs']}
            productive = [q for q in d['cycles'] if q['mode'] != 'clean']
            common_dummy_ids = set.intersection(*[
                {w for p in q['pairs'] for w in pairs[p]['members'] if w.startswith('D')}
                for q in productive
            ])
            cross_chamber_overlap = [
                (a['chamber'], a['index'], b['chamber'], b['index'])
                for i, a in enumerate(productive) for b in productive[i+1:]
                if a['chamber'] != b['chamber']
                and min(a['end'], b['end']) > max(a['start'], b['start']) + 2e-4
            ]
            assert {'D1', 'D2'} <= common_dummy_ids
            assert not cross_chamber_overlap
            row['runs'].append({
                'method': method, 'output': str(run),
                **{k: d.get(k) for k in ('status', 'cmax', 'dual_bound', 'gap', 'solutions',
                                        'solve_seconds', 'variables', 'constraints')},
                'physical_replay': physical,
                'assignment_satisfies_unrestricted_MILP': True,
                'exact_pair_and_cycle_structure_unchanged': signature(d) == signature(reference),
                'structural_variables_checked': len(structural),
                'structural_variables_changed': delta,
                'dummies_in_every_productive_cycle': sorted(common_dummy_ids),
                'cross_chamber_exposure_overlap': cross_chamber_overlap,
                'solution_sha256': digest(run / 'variables.json'),
                'manifest_sha256': digest(run / 'manifest.json'),
            })
        m.freeProb()
        report['instances'].append(row)
    assert len(report['instances']) == 2
    if args.witness:
        run = args.witness.resolve()
        d = read(run / 'result.json')
        mf = read(run / 'manifest.json')
        refdir = resolve_asset(mf['fixed_reference']).parent
        ref = read(refdir / 'reference.json')
        provenance = read(refdir / 'manifest.json')
        original_dir = resolve_asset(provenance['original_reference'])
        original = read(original_dir / 'reference.json')
        assert provenance['assets'] == mf['assets'] == current_assets
        assert provenance['original_reference_sha256'] == digest(original_dir / 'reference.json')
        assert provenance['protocol_sha256'] == digest(ROOT / 'JMS-version/tools/prepare_auxiliary_partition.py')
        assert mf['lp_sha256'] == digest(run / 'model.lp.gz')
        assert mf['fixed_reference_sha256'] == digest(refdir / 'reference.json')
        warm_path = resolve_asset(mf['warm_start'])
        assert mf['warm_start_sha256'] == digest(warm_path)
        warm_result = read(warm_path.parent / 'result.json') if (warm_path.parent / 'result.json').exists() else ref
        assert warm_result['config'] == d['config'] == mf['config']
        if (warm_path.parent / 'result.json').exists():
            warm_mf = read(warm_path.parent / 'manifest.json')
            assert warm_mf['assets'] == current_assets and warm_mf['config'] == d['config']
            assert warm_mf['fixed_reference_sha256'] == mf['fixed_reference_sha256']
            assert warm_mf['lp_sha256'] == digest(warm_path.parent / 'model.lp.gz')
        assert mf['time_limit'] > 0 and mf['stage2_limit'] == 0 and mf['seed'] == 1
        assert d['solve_seconds'] <= mf['time_limit'] + 2
        assert check_assignment(d['config'], read(warm_path)['values'], ref)
        assert read(run / 'warm_start_check.json')['accepted']
        assert signature(ref)['cycles'] == signature(original)['cycles'] == signature(d)['cycles']
        assert original['config'] == ref['config'] == d['config']
        for old, new in zip(signature(original)['pairs'], signature(d)['pairs']):
            assert {k: old[k] for k in ('id', 'chamber', 'mode')} == {k: new[k] for k in ('id', 'chamber', 'mode')}
            for a, b in zip(old['members'], new['members']):
                assert (a == b) if not a.startswith('D') else b.startswith('D')
        physical = validate(d)
        assert physical['valid'], physical['errors']
        values = read(run / 'variables.json')['values']
        assert check_assignment(d['config'], values)
        assert check_assignment(d['config'], values, ref)
        baseline = next(r for row in report['instances'] for r in row['runs']
                        if row['common_cmax'] == original['cmax'] and r['method'] == 'scip_fixed')
        assert baseline['status'] == 'optimal' and baseline['gap'] == 0
        report['auxiliary_witness'] = {
            'output': str(run), 'same_config_product_pairing_chambers_and_cycles': True,
            'assignment_satisfies_unrestricted_MILP': True, 'physical_replay': physical,
            **{k: d.get(k) for k in ('status', 'cmax', 'dual_bound', 'gap', 'solve_seconds', 'solutions')},
            'reference_optimum': baseline['cmax'],
            'strict_improvement_witness': physical['product_return_cmax'] < baseline['dual_bound']-2e-4,
            'dummy_mapping': provenance['dummy_mapping'],
            'warm_start_cmax': warm_result['cmax'],
            'time_limit': mf['time_limit'],
            'warm_start_sha256': digest(warm_path),
            'cross_chamber_exposure_overlap': exposure_overlaps(d),
            'exposure_overlap_seconds': sum(q['end']-q['start'] for q in exposure_overlaps(d)),
            'relative_reduction_percent': 100*(baseline['cmax']-d['cmax'])/baseline['cmax'],
            'product_returns': {j['identity']: j['loan_end'] for j in d['jobs'] if j['product']},
            'manifest_sha256': digest(run / 'manifest.json'),
            'solution_sha256': digest(run / 'variables.json'),
        }
    if args.strong_start:
        report['strong_start_runs'] = []
        for run in sorted(args.strong_start.resolve().glob('n*_H10_mixed_dual')):
            d = read(run / 'result.json')
            mf = read(run / 'manifest.json')
            warm_path = resolve_asset(mf['warm_start'])
            assert mf['assets'] == current_assets
            assert mf['config'] == d['config']
            assert not mf['fixed_reference']
            assert mf['time_limit'] == 1800 and mf['stage2_limit'] == 0 and mf['seed'] == 1
            assert mf['initialization'] == 'none' and mf['initialization_budget'] == 0
            assert mf['lp_sha256'] == digest(run / 'model.lp.gz')
            assert mf['warm_start_sha256'] == digest(warm_path)
            assert read(run / 'warm_start_check.json')['accepted']
            warm_mf = read(warm_path.parent / 'manifest.json')
            assert warm_mf['assets'] == current_assets and warm_mf['config'] == d['config']
            baseline = next(r for row in report['instances'] for r in row['runs']
                            if row['config'] == d['config'] and r['method'] == 'scip_fixed')
            assert warm_path == Path(baseline['output']) / 'variables.json'
            warm_result = read(warm_path.parent / 'result.json')
            physical = validate(d)
            assert physical['valid'], physical['errors']
            assert abs(physical['product_return_cmax']-d['cmax']) < 2e-4
            assert d['full_candidate_space'] and d['result_eligible']
            values = read(run / 'variables.json')['values']
            warm_values = read(warm_path)['values']
            assert check_assignment(d['config'], warm_values)
            assert check_assignment(d['config'], values)
            structural_prefixes = ('jp_', 'jc_used', 'jc_kind', 'jc_occ', 'jc_first',
                                   'jc_last', 'jc_product_pair', 'jc_mixed_product', 'front_')
            changed = [k for k, v in values.items() if k.startswith(structural_prefixes)
                       and abs(v-warm_values[k]) > 2e-4]
            report['strong_start_runs'].append(dict(
                output=str(run), assignment_satisfies_unrestricted_MILP=True,
                physical_replay=physical, warm_start_cmax=warm_result['cmax'],
                structural_variables_changed=changed,
                exact_pair_and_cycle_structure_unchanged=signature(d)==signature(warm_result),
                solution_sha256=digest(run / 'variables.json'),
                manifest_sha256=digest(run / 'manifest.json'),
                warm_start_sha256=digest(warm_path),
                **{k:d.get(k) for k in ('status','cmax','dual_bound','solve_seconds','solutions')}))
        assert len(report['strong_start_runs']) == 2
    report['valid'] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in report['instances']:
        print('Initial', row['common_cmax'])
        for d in row['runs']:
            print({k: v for k, v in d.items() if k not in ('output', 'physical_replay', 'solution_sha256', 'manifest_sha256')})
    for key in ('auxiliary_witness', 'strong_start_runs'):
        if key in report:
            print(key, json.dumps(report[key], ensure_ascii=False))


if __name__ == '__main__':
    main()
