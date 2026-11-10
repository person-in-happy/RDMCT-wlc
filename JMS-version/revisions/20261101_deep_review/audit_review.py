"""Read-only reviewer diagnostics. No solver construction or optimization."""
from pathlib import Path
from collections import defaultdict, Counter
from statistics import mean, stdev
import hashlib
import json

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]


def read(p):
    return json.loads(p.read_text('utf-8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def metrics(d):
    cfg = d['config']
    events = defaultdict(dict)
    for e in d['events']:
        if 'job' in e:
            events[e['job']][e['kind']] = e
    product = [j for j in d['jobs'] if j['product']]
    waits = defaultdict(float)
    dwells = defaultdict(float)
    for j in d['jobs']:
        tag = 'product' if j['product'] else 'auxiliary'
        es = events[j['name']]
        vals = [j['load_start'] - es['source_pick']['end'] - cfg['vtr_travel'],
                es['destination_put']['start'] - j['unload_end'] - cfg['vtr_travel']]
        dwells[tag + '_chamber'] = max(dwells[tag + '_chamber'], j['unload_start'] - j['load_end'])
        dwells[tag + '_robot'] = max(dwells[tag + '_robot'], j['load_end'] - es['source_pick']['start'],
                                    es['destination_put']['end'] - j['unload_start'])
        if j['origin'] != 'VS':
            if 'al_put' in es:
                legs = [('origin_pick', 'al_put', cfg['atr_travel']),
                        ('al_put', 'al_pick', cfg['alignment']),
                        ('al_pick', 'upper_put', cfg['atr_travel'])]
                dwells[tag + '_al'] = max(dwells[tag + '_al'], es['al_pick']['start'] - es['al_put']['end'])
                hand = [es['al_put']['end'] - es['origin_pick']['start'],
                        es['upper_put']['end'] - es['al_pick']['start']]
            else:
                legs = [('origin_pick', 'upper_put', cfg['atr_travel'])]
                hand = [es['upper_put']['end'] - es['origin_pick']['start']]
            legs += [('upper_put', 'source_pick', cfg['pump']),
                     ('destination_put', 'lower_pick', cfg['vent']),
                     ('lower_pick', 'origin_put', cfg['atr_travel'])]
            vals += [es[b]['start'] - es[a]['end'] - t for a, b, t in legs]
            dwells[tag + '_robot'] = max(dwells[tag + '_robot'], *hand,
                                        es['origin_put']['end'] - es['lower_pick']['start'])
            dwells[tag + '_ll'] = max(dwells[tag + '_ll'],
                es['source_pick']['start'] - es['upper_put']['end'],
                es['lower_pick']['start'] - es['destination_put']['end'])
        assert min(vals) > -2e-4
        waits[tag] += sum(max(0, t) for t in vals)
    cycles = [c for c in d['cycles'] if c['mode'] != 'clean']
    overlap = sum(max(0, min(a['end'], b['end']) - max(a['start'], b['start']))
                  for i, a in enumerate(cycles) for b in cycles[i + 1:] if a['chamber'] != b['chamber'])
    return dict(product_pick_sum=sum(j['loan_start'] for j in product),
        product_return_sum=sum(j['loan_end'] for j in product),
        product_flow_sum=sum(j['loan_end'] - j['loan_start'] for j in product),
        product_chamber_sum=sum(j['unload_start'] - j['load_end'] for j in product),
        product_route_wait=waits['product'], auxiliary_route_wait=waits['auxiliary'],
        product_count=len(product), product_cmax=max(j['loan_end'] for j in product),
        production_overlap_seconds=overlap, max_dwells=dict(dwells))


def main():
    snapshots = {}
    def checked(p, expected=None):
        h = sha(p)
        if expected:
            assert h == expected, p
        snapshots[str(p)] = h
        return read(p)
    old = checked(HERE.parent / '20261031_final_manuscript/verified_results.json')
    prior = checked(HERE.parent / '20261101_supplement_update/verified_supplements.json')
    new = checked(HERE.parent / '20261101_strengthening_update/verified_strengthening.json')
    source = PAPER / 'JMS_Review_CN.tex'
    source_hash = sha(source)
    snapshots[str(source)] = source_hash
    pdf_hash = sha(PAPER / 'JMS_Review_CN.pdf')
    rows, paired = [], []
    configs = set()
    for r in old['rows']:
        base = PAPER / 'results' / r['campaign'] / 'runs' / r['id']
        d = checked(base / 'result.json', r['hashes']['result.json'])
        initial = checked(base / 'phase1.json', r['hashes']['phase1.json'])
        if not r['has_solution']:
            continue
        ms = metrics(d)
        assert abs(ms['product_route_wait'] + ms['auxiliary_route_wait'] - r['metrics']['route_wait_sum']) < 2e-3
        configs.add(json.dumps(d['config'], sort_keys=True))
        rows.append(dict(campaign=r['campaign'], id=r['id'], suite=r['suite'], arm=r['variant'],
                         metrics=ms, path=str(base / 'result.json')))
        if r['variant'] == 'refined' and r['suite'] in ('paper', 'qualification'):
            before = metrics(initial)
            # Fixed route durations imply this telescoping identity for products.
            delta_flow = ms['product_flow_sum'] - before['product_flow_sum']
            delta_wait = ms['product_route_wait'] - before['product_route_wait']
            delta_chamber = ms['product_chamber_sum'] - before['product_chamber_sum']
            assert abs(delta_flow - delta_wait - delta_chamber) < 2e-3
            paired.append(dict(case=r['case'], seed=r['seed'], before=before, after=ms,
                               before_path=str(base / 'phase1.json'), after_path=str(base / 'result.json')))
    for report in (prior, new):
        for r in report['rows']:
            p = PAPER / 'results' / r['campaign'] / 'runs' / r['id'] / 'result.json'
            d = checked(p, r['hashes']['result.json'])
            ms = metrics(d)
            saved = r.get('metrics', r.get('actual'))
            assert abs(ms['product_route_wait'] + ms['auxiliary_route_wait'] - saved['route_wait_sum']) < 2e-3
            configs.add(json.dumps(d['config'], sort_keys=True))
            rows.append(dict(campaign=r['campaign'], id=r['id'], suite=r['suite'], arm=r['arm'],
                             metrics=ms, path=str(p)))
    assert len(rows) == 603
    grouped = defaultdict(list)
    for r in paired:
        grouped[r['case']].append(r)
    phase_changes = []
    for case, group in grouped.items():
        entry = dict(case=case, n=len(group))
        for phase in ('before', 'after'):
            entry[phase] = {k: mean(r[phase][k] for r in group)
                            for k, val in group[0][phase].items() if isinstance(val, (int, float))}
        a, b = entry['before'], entry['after']
        drop = a['product_route_wait'] - b['product_route_wait']
        entry['route_wait_reduction_percent'] = 100 * drop / a['product_route_wait']
        entry['flow_reduction_percent'] = 100 * (a['product_flow_sum'] - b['product_flow_sum']) / a['product_flow_sum']
        entry['chamber_increase_over_wait_drop_percent'] = 100 * (b['product_chamber_sum'] - a['product_chamber_sum']) / drop
        phase_changes.append(entry)
    search = []
    groups = defaultdict(list)
    for r in old['rows']:
        groups[r['suite'], r['variant']].append(r)
    for (suite, arm), group in groups.items():
        warmed = [r for r in group if r['has_solution'] and r['initial_cmax'] is not None]
        search.append(dict(suite=suite, arm=arm, records=len(group), warm_records=len(warmed),
            primary_improvements=sum(r['phase1_cmax'] < r['initial_cmax'] - 1e-4 for r in warmed),
            optimal_primary=sum(r['status'] == 'optimal' for r in group)))
    stats = defaultdict(list)
    for r in rows:
        stats[r['suite'], r['arm']].append(r)
    parallel = [dict(suite=suite, arm=arm, records=len(group),
                     with_production_overlap=sum(r['metrics']['production_overlap_seconds'] > 1e-4 for r in group))
                for (suite, arm), group in stats.items()]
    timing = []
    g = defaultdict(list)
    for r in new['rows']:
        if r['suite'] == 'representation':
            g[r['case'], r['arm']].append(r['build_and_start_check_seconds'])
    for (case, arm), values in g.items():
        timing.append(dict(case=case, arm=arm, observations=values, mean=mean(values), sample_sd=stdev(values)))
    implementation = PAPER / 'experiments/strengthening_20261101/strengthen_models.py'
    snapshots[str(implementation)] = sha(implementation)
    code = implementation.read_text('utf-8')
    assert 'x.original_dimensions = dimensions(x)' in code
    assert 'dim = dimensions(x)' in code
    assert code.index('begin = time.monotonic()') < code.index('x = build(cfg, cell[\'arm\'], original)')
    for path, expected in snapshots.items():
        assert sha(Path(path)) == expected, path
    assert sha(PAPER / 'JMS_Review_CN.pdf') == pdf_hash
    report = dict(source_sha256=source_hash, pdf_sha256=pdf_hash,
        feasible_records_checked=603, unique_full_input_configs=len(configs),
        result_and_phase_files_hash_checked=sum(Path(p).name in ('result.json', 'phase1.json') for p in snapshots),
        production_overlap_records=sum(r['metrics']['production_overlap_seconds'] > 1e-4 for r in rows),
        product_chamber_increase_runs=sum(r['after']['product_chamber_sum'] > r['before']['product_chamber_sum'] + 1e-4 for r in paired),
        stage_pairs=len(paired), phase_changes=phase_changes, paired_metrics=paired,
        search=search, parallel=parallel, preparation_timing=timing,
        max_dwells={k: max(r['metrics']['max_dwells'].get(k, 0) for r in rows)
                    for k in ('product_chamber', 'product_robot', 'product_al', 'product_ll',
                              'auxiliary_chamber', 'auxiliary_robot', 'auxiliary_ll')},
        residency_inputs=sorted({(json.loads(c)['module_residency'], json.loads(c)['robot_residency']) for c in configs}),
        known_preparation_asymmetry='Wafer arm performs one extra dimensions(x) traversal before the common timed traversal.',
        asymmetry_elapsed_seconds='Not instrumented; cannot separate from historical total times.',
        rows=rows, snapshots=snapshots, optimization_started=False, source_and_raw_results_unchanged=True)
    (HERE / 'diagnostics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({k: report[k] for k in ('feasible_records_checked', 'unique_full_input_configs',
        'result_and_phase_files_hash_checked', 'production_overlap_records',
        'product_chamber_increase_runs', 'stage_pairs', 'max_dwells', 'residency_inputs')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
