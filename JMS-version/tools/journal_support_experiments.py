"""New D-model coupling and frozen-policy transfer protocols (2026-11-09).

No old campaign/launcher is modified. plan/prepare/check do not optimize.
start/resume use the existing foreground queue with dynamic available-RAM
protection, native unlimited SCIP memory, one worker and one solver thread.
All comparisons are conditional module tests, not end-to-end wall-budget tests.
"""
from pathlib import Path
from dataclasses import asdict
from collections import Counter, defaultdict
import argparse
import hashlib
import json
import shutil
import sys
import time

import journal_gap_experiments as base

HERE = Path(__file__).resolve()
ROOT, JMS, RESULTS = base.ROOT, base.JMS, base.RESULTS
read, dump, digest = base.read, base.dump, base.digest
ASSET_PATHS = tuple(base.inventory()) + (str(HERE.relative_to(ROOT)),)
SUITES = ('mechanism', 'chain', 'qualification', 'transfer', 'backfill_standard', 'rhythm')
OLD_STANDARD = RESULTS / 'journal_d_standard_t1_20261108_unlimited_r1'


def inventory():
    return {p: digest(ROOT / p) for p in ASSET_PATHS}


def config_key(cfg):
    # JSON normalizes tuples/lists without changing the scheduling semantics.
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()


def make_config(n, recipe, layout, h, dummy):
    ports = {f'LP{i}': {'4x1': 0, '2x2': 0} for i in range(1, 5)}
    for i in range(n):
        mode = recipe if recipe != 'mixed' else ('4x1' if i < n // 2 else '2x2')
        lp = 1 if layout == 'concentrated' else i % 4 + 1 if layout == 'spread' else (1 if i < (n + 1) // 2 else 2)
        ports[f'LP{lp}'][mode] += 1
    return asdict(base.backend.Config(ports, cleaning_interval=h, dummy_count=dummy))


def test_cases():
    # Prospective coverage design, not a factorial estimate of separate effects.
    # The scenarios deliberately vary correlated factors; do not attribute their
    # aggregate differences to H, inventory or LP layout alone.
    cases = []
    for n in (2, 4, 8):
        for recipe in ('4x1', '2x2', 'mixed'):
            for scenario, (layout, h, dummy) in enumerate((('concentrated', 2, 4), ('spread', 3, 6), ('skew', 5, 8)), 1):
                cases.append((f'n{n}_{recipe}_scenario{scenario}', make_config(n, recipe, layout, h, dummy)))
    assert len({config_key(c) for _, c in cases}) == 27
    return cases


def mechanism_cases():
    cases = []
    # Paired H/inventory/cleaning-rule contrasts within each of six workloads.
    for n, recipe in ((1, '4x1'), (1, '2x2'), (2, 'mixed'), (4, '4x1'), (4, '2x2'), (4, 'mixed')):
        for h in (2, 3):
            for dummy in (4, 8):
                cases.append((f'n{n}_{recipe}_H{h}_D{dummy}', make_config(n, recipe, 'spread', h, dummy)))
    return cases


def existing_inputs():
    found = {}
    for campaign in (base.SMALL, base.PAPER):
        for result in sorted((campaign / 'runs').glob('*/phase1.json')):
            values = result.with_name('variables_phase1.json')
            d = read(result)
            if values.exists() and d.get('original_model_check') and d.get('solutions') and base.validate(d)['valid']:
                found.setdefault(config_key(d['config']), (str(result), str(values)))
    return found


def metrics(data):
    out = base.review.physical_metrics(data)
    loans = [j for j in data['jobs'] if not j['product']]
    counts = Counter(j['identity'] for j in loans)
    points = [(j['loan_start'], 1) for j in loans] + [(j['loan_end'], -1) for j in loans]
    current = peak = 0
    for _, delta in sorted(points):  # return before reborrow at a shared endpoint
        current += delta
        peak = max(peak, current)
    pair_cycles = Counter(p for c in data['cycles'] if c['mode'] == '2x2' for p in c['pairs'])
    continuous = sum(p['mode'] == '2x2' and pair_cycles[p['id']] == 2 and
                     any(j['product'] and j['pair'] == p['id'] for j in data['jobs']) for p in data['pairs'])
    out.update(auxiliary_loans=len(loans), distinct_auxiliaries=len(counts),
               reused_auxiliaries=sum(n > 1 for n in counts.values()),
               repeat_loans=sum(n - 1 for n in counts.values()), peak_auxiliary_loans=peak,
               continuous_product_pairs=continuous)
    out['coupled_witness'] = bool(out['cleanings'] and continuous and out['repeat_loans'])
    return out


def parent_sources(path, required_suite):
    parent = base.campaign_path(path)
    spec = checked(parent)
    if spec['suite'] != required_suite:
        raise ValueError('Expected parent suite ' + required_suite)
    cov = summarize(parent)
    if cov['complete'] != cov['expected']:
        raise ValueError('Finish every parent cell, including no-incumbent outcomes, before selection')
    selected, excluded = {}, []
    for c in sorted(spec['cells'], key=lambda r: (r['case'], r['seed'])):
        dest = parent / 'runs' / c['id']
        e = read(dest / 'evidence.json')
        if e['valid'] and (required_suite != 'chain' or e['metrics']['rhythm_centers'] >= 1):
            selected.setdefault(c['case'], (c['config'], str(dest / 'result.json'), str(dest / 'variables.json')))
        else:
            excluded.append(dict(case=c['case'], seed=c['seed'], state=e['state']))
    provenance = dict(path=str(parent), campaign_sha256=digest(parent / 'campaign.json'),
                      coverage=cov, all_nonincumbent_cells=excluded,
                      eligible_cases=sorted(selected),
                      selection='Lowest predefined solver seed with a validated assignment; no objective/algorithm-gain selection')
    if not selected:
        raise ValueError('No qualified inputs. Preserve all failures; do not start conditional comparisons.')
    return selected, provenance


def plan(a):
    cells, provenance = [], None
    def cell(case, cfg, seed, arm, method='scip', training_seed=1, **kw):
        cells.append(dict(id=f'{case}__s{seed}__t{training_seed}__{arm}', case=case,
                          config_data=cfg, seed=seed, arm=arm, method=method,
                          training_seed=training_seed, policy=base.policy_record(method, training_seed), **kw))
    if a.suite in ('mechanism', 'qualification', 'chain'):
        sources = existing_inputs() if a.suite == 'mechanism' else {}
        cases = mechanism_cases() if a.suite == 'mechanism' else test_cases() if a.suite == 'qualification' else [
            (f'n{n}_2x2_H{h}_D{d}', make_config(n, '2x2', 'spread', h, d))
            for n in (4, 6) for h in (3, 5) for d in (4, 8)]
        for case, cfg in cases:
            warm = sources.get(config_key(cfg))
            if warm and not base.review.physical_metrics(read(warm[0]))['legacy_rule_feasible']:
                warm = None  # give BOTH rules the same input, or neither
            for seed in ((17,) if a.suite == 'qualification' else (1, 2, 3)):
                for arm in (('optional', 'legacy') if a.suite == 'mechanism' else (a.suite,)):
                    cell(case, cfg, seed, arm, cut_profile='standard',
                         **(dict(source=warm[0], values=warm[1]) if warm else {}))
    elif a.suite == 'backfill_standard':
        old = read(OLD_STANDARD / 'campaign.json')
        # Reuse its inputs, seeds, cut profile and budget. Never rerun t1 or SCIP.
        for c in old['cells']:
            if c['method'] == 'scip':
                continue
            for t in (2, 3):
                cell(c['case'], read(c['config']), c['seed'], c['arm'], c['method'], t,
                     spbs=c['spbs'], cut_profile=c['cut_profile'], source=c['source'], values=c['values'])
        provenance = dict(path=str(OLD_STANDARD), campaign_sha256=digest(OLD_STANDARD / 'campaign.json'),
                          reuse='72 completed t1/SCIP cells; append ONLY 96 t2/t3 cells',
                          old_settings=old['settings'])
    else:
        if not a.source_campaign:
            raise ValueError('--source-campaign required')
        sources, provenance = parent_sources(a.source_campaign, 'qualification' if a.suite == 'transfer' else 'chain')
        for case, (config, source, values) in sources.items():
            for seed in (1, 2, 3):
                if a.suite == 'rhythm':
                    for w in (0, 5, 25, 100):
                        cell(case, read(config), seed, f'weight{w}', weight=w, source=source, values=values)
                else:
                    # One common SPBS output per instance/solver seed, shared by
                    # every learned policy. This avoids attributing different
                    # initialization outcomes to the learned cut selector.
                    cell(case, read(config), seed, 'shared_spbs', spbs=True,
                         cut_profile='standard', source=source, values=values)
                    arms = [('scip', False), ('hem', False), ('proposed', False),
                            ('scip', True), ('hem', True), ('proposed', True),
                            ('feature_only', True), ('proposed_no_structure', True), ('proposed_greedy', True)]
                    for method, spbs in arms:
                        for t in ((1,) if method == 'scip' else (1, 2, 3)):
                            cell(case, read(config), seed, method + ('_spbs' if spbs else '_plain'), method, t,
                                 spbs=spbs, cut_profile='standard', source=source, values=values)
    return cells, provenance


def prepare(a, out):
    import psutil
    if out.exists():
        raise FileExistsError('Use a new campaign path or resume the unchanged campaign')
    if not (a.time_limit > 0 and a.wall_limit > a.time_limit and 0 < a.min_available_fraction < .5):
        raise ValueError('Need positive solve budget, larger safety wall guard and 0 < RAM fraction < .5')
    cells, provenance = plan(a)
    if a.suite == 'backfill_standard' and a.time_limit != provenance['old_settings']['time_limit']:
        raise ValueError('Backfill must retain the old 300-second nominal budget')
    from scip_imports import scip
    probe = scip.Model()
    memory = probe.getParam('limits/memory')
    probe.freeProb()
    assert memory > 1e12
    settings = dict(time_limit=a.time_limit, stage2_limit=0, cleanup_limit=a.time_limit,
                    memory_mb=memory, process_memory_mb=None,
                    memory_policy='scip_native_unlimited_system_available_fraction',
                    min_available_fraction=a.min_available_fraction, wall_limit=a.wall_limit,
                    threads=1, jobs=1, available_at_prepare_mib=psutil.virtual_memory().available / 1024**2)
    out.mkdir(parents=True)
    (out / 'configs').mkdir()
    sources = {}
    for c in cells:
        cfg = c.pop('config_data')
        base.config_check(cfg)
        target = out / 'configs' / (c['case'] + '.json')
        if target.exists() and config_key(read(target)) != config_key(cfg):
            raise ValueError('Case identifier collision')
        dump(target, cfg)
        c['config'] = str(target)
        for key in ('config', 'source', 'values'):
            if key in c:
                sources[c[key]] = digest(Path(c[key]))
        if c['policy']:
            for key in ('checkpoint', 'config'):
                sources[c['policy'][key]] = digest(Path(c['policy'][key]))
    if provenance:
        sources[str(Path(provenance['path']) / 'campaign.json')] = provenance['campaign_sha256']
    spec = dict(schema=1, suite=a.suite, created_utc=base.stamp(), cells=cells, settings=settings,
                assets=inventory(), environment=base.environment(), sources=sources, parent=provenance,
                backend=str(base.BACKEND),
                timing='Solver budgets; build/export/policy load/validation separately recorded. Supplied-input transfer/SPBS is NOT end-to-end wall-budget evidence.',
                inference='Frozen CIE policy transfer. Unit of generalization = distinct prospectively specified instance, not solver/training repetitions. Conditional eligible subset and all qualification failures reported.',
                selection='Prospective 27-case coverage design. Scenario factors correlated, not a factorial sensitivity study. No outcome-driven removal.',
                primary_contrast='proposed_spbs versus hem_spbs; aggregate seeds within each instance before paired analysis')
    dump(out / 'campaign.json', spec)
    dump(out / 'contract.json', dict(campaign_sha256=digest(out / 'campaign.json')))
    for rel in spec['assets']:
        target = out / 'frozen_code' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    print(json.dumps(dict(prepared=str(out), cells=len(cells), settings=settings, solver_started=False)), flush=True)


def checked(out):
    spec = read(out / 'campaign.json')
    if digest(out / 'campaign.json') != read(out / 'contract.json')['campaign_sha256']:
        raise RuntimeError('Frozen protocol changed')
    if spec['assets'] != inventory() or spec['environment'] != base.environment():
        raise RuntimeError('Code/environment changed; keep old campaign and create a new one')
    for p, expected in spec['sources'].items():
        if digest(Path(p)) != expected:
            raise RuntimeError('Frozen source changed: ' + p)
    if spec['settings']['memory_policy'] != 'scip_native_unlimited_system_available_fraction':
        raise RuntimeError('Fixed-memory campaigns are unsupported')
    return spec


def checked_result(data, variables):
    if not data.get('original_model_check') or not base.validate(data)['valid']:
        raise RuntimeError('Original-model or independent physical validation failed')
    return base.strengthening.audit_full(base.backend.Config(**data['config']), read(variables)['values'], data)


def basic_run(c, dest, settings, suite, check_only):
    cfg = base.backend.Config(**read(c['config']))
    if check_only:
        x = base.backend.Integrated(cfg)
        try:
            if c.get('values'):
                base.review.canonical_warm(x, read(c['values'])['values'])
            return dict(valid=True, solver_started=False, variables=x.model.getNVars(), constraints=x.model.getNConss())
        finally:
            x.model.freeProb()
    began = time.monotonic()
    base.solve(c['config'], dest / 'solve', time_limit=settings['time_limit'], stage2_limit=0,
               seed=c['seed'], initialization='none', memory_mb=settings['memory_mb'],
               warm_start=c.get('values'), cleaning_rule=c['arm'] if suite == 'mechanism' else 'optional',
               cut_profile='standard')
    wall = time.monotonic() - began
    data = read(dest / 'solve/result.json')
    shutil.copy2(dest / 'solve/result.json', dest / 'result.json')
    valid = bool(data.get('solutions'))
    record = dict(valid=valid, state=data['primary_status'], primary_bound=base.followup.finite_bound(data['primary_bound']),
                  primary_gap=base.followup.finite_bound(data.get('primary_gap')), solve_seconds=data['solve_seconds'], call_wall_seconds=wall,
                  allocated_solver_seconds=settings['time_limit'],
                  budget_overrun_seconds=max(0., data['solve_seconds'] - settings['time_limit']))
    if c.get('values') and not read(dest / 'solve/warm_start_check.json')['accepted']:
        raise RuntimeError('Common warm start rejected; do not silently change the comparison')
    if valid:
        shutil.copy2(dest / 'solve/variables.json', dest / 'variables.json')
        record.update(metrics=metrics(data), full_model_audit=checked_result(data, dest / 'variables.json'))
    return record


def chain_run(c, dest, settings, check_only):
    x = base.backend.Integrated(base.backend.Config(**read(c['config'])))
    m = x.model
    begin = time.monotonic()
    try:
        centers = [x.and_(x.keep[ch, q], x.keep[ch, q-1], f'support_center_{ch}_{q}')
                   for ch in x.cfg.chambers for q in range(2, x.Q)]
        m.addCons(sum(centers) >= 1, name='diagnostic_one_active_center')
        m.addCons(sum(x.cy.kind[ch, q, 'clean'] for ch in x.cfg.chambers for q in range(x.Q)) >= 1,
                  name='diagnostic_actual_cleaning')
        reused = []
        for i in range(1, x.cfg.dummy_count + 1):
            z = m.addVar(vtype='B', name=f'diagnostic_reused_D{i}')
            m.addCons(sum(x.pair.dummy_identity[f'D{i}', p, r] for p in range(x.P) for r in (0, 1)) >= 2*z)
            reused.append(z)
        m.addCons(sum(reused) >= 1, name='diagnostic_finite_reuse')
        if check_only:
            return dict(valid=True, solver_started=False, variables=m.getNVars(), constraints=m.getNConss())
        m.setIntParam('parallel/maxnthreads', 1)
        m.setIntParam('randomization/randomseedshift', c['seed'])
        m.setRealParam('limits/memory', settings['memory_mb'])
        m.setRealParam('limits/time', settings['time_limit'])
        m.setLogfile(str(dest / 'solver.log'))
        m.writeProblem(str(dest / 'restricted_model.lp'), verbose=False)
        m.optimize()
        data = x.result()
        data.update(base.incumbent_checks(m), full_candidate_space=False,
                    experiment_scope='restricted_coupling_witness_search_not_global_optimum')
        data['validation'] = base.validate(data)
        dump(dest / 'result.json', base.finite(data))
        valid = bool(m.getNSols())
        record = dict(valid=valid, state=str(m.getStatus()), primary_optimality_claim=False,
                      solve_seconds=m.getSolvingTime(), call_wall_seconds=time.monotonic()-begin,
                      allocated_solver_seconds=settings['time_limit'],
                      budget_overrun_seconds=max(0., m.getSolvingTime()-settings['time_limit']),
                      restricted_lp_sha256=digest(dest / 'restricted_model.lp'))
        if valid:
            dump(dest / 'variables.json', dict(values=base.followup.save_assignment(x, m.getBestSol())))
            record['metrics'] = metrics(data)
            if not record['metrics']['coupled_witness'] or record['metrics']['rhythm_centers'] < 1:
                raise RuntimeError('Witness did not activate the requested mechanisms')
    finally:
        m.freeProb()
    if valid:
        record['unrestricted_model_audit'] = checked_result(data, dest / 'variables.json')
    return record


def shared_spbs_run(c, dest, settings):
    x = base.backend.Integrated(base.backend.Config(**read(c['config'])))
    m = x.model
    try:
        values = base.review.canonical_warm(x, read(c['values'])['values'])
        m.setIntParam('parallel/maxnthreads', 1)
        m.setIntParam('randomization/randomseedshift', c['seed'])
        m.setRealParam('limits/memory', settings['memory_mb'])
        m.setLogfile(str(dest / 'spbs.log'))
        started = time.monotonic()
        values, levels = base.improve_skeleton(x, values, settings['time_limit'] * .2)
        elapsed = time.monotonic() - started
        sol = base.strengthening.assignment_solution(x, values)
        data = x.result(solution=sol)
        m.freeSol(sol)
        data.update(solutions=1, status='shared_preparation', original_model_check=True,
                    experiment_scope='shared_SPBS_input_not_global_optimum')
        data['validation'] = base.validate(data)
        dump(dest / 'result.json', base.finite(data))
        dump(dest / 'variables.json', dict(values=values))
        dump(dest / 'spbs_levels.json', levels)
    finally:
        m.freeProb()
    return dict(valid=True, state='shared_preparation', metrics=metrics(data),
                source_metrics=metrics(read(c['source'])), initialization_wall_seconds=elapsed,
                allocated_solver_seconds=settings['time_limit']*.2, spbs_levels=levels,
                full_model_audit=checked_result(data, dest / 'variables.json'))


def shared_input(out, c):
    identifier = f"{c['case']}__s{c['seed']}__t1__shared_spbs"
    folder = out / 'runs' / identifier
    e = read(folder / 'evidence.json')
    if (folder / 'failure.json').exists() or read(folder / 'resources.json')['exit_code'] != 0 or not e['valid']:
        raise RuntimeError('Shared SPBS preparation incomplete/invalid')
    for name, key in (('result.json', 'result_sha256'), ('variables.json', 'variables_sha256')):
        if digest(folder / name) != e[key]:
            raise RuntimeError('Shared SPBS input changed')
    return folder, e


def worker(out, identifier, check_only=False):
    spec = checked(out)
    c = next(c for c in spec['cells'] if c['id'] == identifier)
    if c['policy'] != base.policy_record(c['method'], c['training_seed']):
        raise RuntimeError('Policy changed')
    dest = out / ('checks' if check_only else 'runs') / (identifier + ('_' + str(time.time_ns()) if check_only else ''))
    dest.mkdir(parents=True, exist_ok=False)
    if spec['suite'] == 'transfer' and c['arm'] == 'shared_spbs' and not check_only:
        record = shared_spbs_run(c, dest, spec['settings'])
    elif spec['suite'] in ('transfer', 'backfill_standard'):
        actual, settings = c, spec['settings']
        shared = None
        if spec['suite'] == 'transfer' and c['spbs'] and not check_only:
            shared, preparation = shared_input(out, c)
            actual = c | dict(spbs=False, source=str(shared / 'result.json'), values=str(shared / 'variables.json'))
            settings = settings | dict(time_limit=settings['time_limit']*.8)
        record = base.algorithm_run(actual, dest, settings, check_only)
        if shared is not None:
            record.update(shared_spbs_input=str(shared),
                          shared_spbs_variables_sha256=preparation['variables_sha256'],
                          initialization_wall_seconds=preparation['initialization_wall_seconds'],
                          original_input_metrics=metrics(read(c['source'])),
                          spbs_levels=preparation['spbs_levels'],
                          timing_note='Shared preparation wall time is charged to EACH SPBS arm for reporting, although computed once.')
        if not check_only:
            data = read(dest / 'result.json')
            allotted = spec['settings']['time_limit'] * (.8 if c['spbs'] else 1.)
            record.update(metrics=metrics(data), solve_seconds=data['solve_seconds'],
                          allocated_solver_seconds=allotted,
                          budget_overrun_seconds=max(0., data['solve_seconds']-allotted))
    elif spec['suite'] == 'rhythm':
        record = base.review.refine(c | dict(arm='refinement'), dest,
                                    spec['settings'] | dict(stage2_limit=spec['settings']['time_limit']), check_only)
        if not check_only:
            record['metrics'] = metrics(read(dest / 'result.json'))
            record['full_model_audit'] = checked_result(read(dest / 'result.json'), dest / 'variables.json')
            record['allocated_solver_seconds'] = spec['settings']['time_limit']
            record['budget_overrun_seconds'] = max(0., record['solve_seconds']-spec['settings']['time_limit'])
    elif spec['suite'] == 'chain':
        record = chain_run(c, dest, spec['settings'], check_only)
    else:
        record = basic_run(c, dest, spec['settings'], spec['suite'], check_only)
    record.update(cell=c, ended_utc=base.stamp(), backend=str(base.BACKEND))
    if not check_only:
        record['result_sha256'] = digest(dest / 'result.json')
        if (dest / 'variables.json').exists():
            record['variables_sha256'] = digest(dest / 'variables.json')
    dump(dest / ('check.json' if check_only else 'evidence.json'), base.finite(record))
    print(json.dumps(dict(cell=identifier, valid=record['valid'], state=record.get('state'), solver_started=not check_only)), flush=True)


# Keep the queue's tested resume/interrupt/archive/resource behavior. The adapter
# changes only process-local bindings; the frozen original source stays intact.
_summarize = base.summarize


def summarize(out):
    return _summarize(out)


def contrasts(rows, bootstrap=10000):
    """Average paired seeds within each case BEFORE resampling cases."""
    import numpy as np
    by = defaultdict(dict)
    for r in rows:
        if r.get('valid'):
            by[(r['case'], r['arm'])][(r['seed'], r['training_seed'])] = r['metrics']['product_cmax']
    pairs = [('hem_spbs', 'proposed_spbs'), ('hem_plain', 'proposed_plain'),
             ('scip_plain', 'scip_spbs'), ('hem_plain', 'hem_spbs'), ('proposed_plain', 'proposed_spbs'),
             ('feature_only_spbs', 'proposed_spbs'), ('proposed_no_structure_spbs', 'proposed_spbs'),
             ('proposed_greedy_spbs', 'proposed_spbs')]
    out = []
    for control, treatment in pairs:
        effects, case_names = [], []
        per_training = defaultdict(list)
        for case in sorted({r['case'] for r in rows}):
            left, right = by.get((case, control), {}), by.get((case, treatment), {})
            if not left or set(left) != set(right):
                continue  # no unmatched success-only comparison
            effects.append(sum((left[k] - right[k]) / left[k] * 100 for k in left) / len(left))
            case_names.append(case)
            for training in sorted({k[1] for k in left}):
                keys = [k for k in left if k[1] == training]
                per_training[training].append(sum((left[k]-right[k])/left[k]*100 for k in keys)/len(keys))
        if effects:
            x = np.array(effects)
            rng = np.random.default_rng(20261109)
            samples = rng.choice(x, (bootstrap, len(x)), replace=True).mean(axis=1)
            out.append(dict(control=control, treatment=treatment, instances=len(x),
                            mean_relative_gain_percent=float(x.mean()), median_relative_gain_percent=float(np.median(x)),
                            wins=int(sum(x > 1e-6)), ties=int(sum(abs(x) <= 1e-6)), losses=int(sum(x < -1e-6)),
                            descriptive_case_bootstrap_95_percent=np.quantile(samples, [.025, .975]).tolist() if len(x) >= 2 else None,
                            by_training_seed={str(t): dict(instances=len(v), mean_relative_gain_percent=float(np.mean(v))) for t, v in per_training.items()},
                            per_case=dict(zip(case_names, effects))))
    return out


def report(out):
    spec = checked(out)
    coverage = summarize(out)
    if coverage['complete'] != coverage['expected']:
        raise ValueError('Report requires complete coverage; use status for partial progress')
    rows = []
    def append_campaign(path, cells):
        for c in cells:
            dest = path / 'runs' / c['id']
            e = read(dest / 'evidence.json')
            if (dest / 'failure.json').exists() or read(dest / 'resources.json')['exit_code'] != 0:
                raise RuntimeError('Failed source cell')
            for name, key in (('result.json', 'result_sha256'), ('variables.json', 'variables_sha256')):
                if key in e and digest(dest / name) != e[key]:
                    raise RuntimeError('Source artifact changed')
            data = read(dest / 'result.json')
            rows.append(dict(case=c['case'], arm=c['arm'], seed=c['seed'], training_seed=c['training_seed'],
                             valid=e['valid'], state=e['state'], metrics=e.get('metrics'),
                             primary_bound=base.followup.finite_bound(e.get('primary_bound')), gap=base.followup.finite_bound(e.get('primary_gap')),
                             solve_seconds=e.get('solve_seconds', data.get('solve_seconds')),
                             primary_only_pdi=e.get('primary_only_pdi'),
                             initialization_wall_seconds=e.get('initialization_wall_seconds'),
                             primary_wall_seconds=e.get('primary_wall_seconds'),
                             callback_calls=(e.get('telemetry') or {}).get('callback_calls'),
                             budget_overrun_seconds=e.get('budget_overrun_seconds'),
                             wall_seconds=read(dest / 'resources.json')['wall_seconds']))
    append_campaign(out, spec['cells'])
    if spec['suite'] == 'backfill_standard':
        append_campaign(OLD_STANDARD, read(OLD_STANDARD / 'campaign.json')['cells'])
    summary = dict(coverage=coverage, merged_rows=len(rows), unique_instances=len({r['case'] for r in rows}),
                   algorithm_rows=sum(r['arm'] != 'shared_spbs' for r in rows),
                   valid=sum(r['valid'] for r in rows), parent=spec['parent'],
                   statuses=dict(Counter(r['state'] for r in rows)),
                   coupled_witnesses=sum(bool((r.get('metrics') or {}).get('coupled_witness')) for r in rows),
                   budget_overrun_rows=[r for r in rows if (r.get('budget_overrun_seconds') or 0) > .001],
                   contrasts=contrasts(rows),
                   caution='Descriptive uncertainty across this synthetic design, not industrial population inference. Repeated solver/training seeds are not independent instances. Report all nonincumbents. No automatic significance/superiority claim.')
    dump(out / 'summary/analysis.json', base.finite(summary))
    dump(out / 'summary/analysis_rows.json', base.finite(rows))
    print(json.dumps(base.finite(summary), ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('action', choices=('plan', 'prepare', 'start', 'resume', 'status', 'check', 'report', '_worker'))
    p.add_argument('--suite', choices=SUITES)
    p.add_argument('--campaign')
    p.add_argument('--source-campaign')
    p.add_argument('--cell')
    p.add_argument('--time-limit', type=float, default=300)
    p.add_argument('--wall-limit', type=float, default=2400)
    p.add_argument('--min-available-fraction', type=float, default=.10)
    p.add_argument('--retry-failed', action='store_true')
    a = p.parse_args()
    if a.action in ('plan', 'prepare', 'start'):
        if not a.suite:
            p.error('--suite required')
    elif any(v.split('=')[0] in ('--suite', '--time-limit', '--wall-limit', '--min-available-fraction', '--source-campaign') for v in sys.argv[1:]):
        p.error('Frozen settings cannot be changed on resume/check/status/report')
    if a.retry_failed and a.action != 'resume':
        p.error('--retry-failed is only valid on resume')
    if a.action == 'plan':
        cells, parent = plan(a)
        print(json.dumps(dict(suite=a.suite, cells=len(cells), instances=len({c['case'] for c in cells}),
                              first_cell=cells[0]['id'] if cells else None, parent=parent, solver_started=False), indent=2))
        return
    if not a.campaign:
        p.error('--campaign required')
    out = base.campaign_path(a.campaign)
    if a.action in ('prepare', 'start'):
        prepare(a, out)
    if a.action in ('start', 'resume'):
        base.__file__ = str(HERE)
        base.checked = checked
        base.summarize = summarize
        base.run(out, a.retry_failed)
    elif a.action == 'status':
        checked(out)
        print(json.dumps(summarize(out)))
    elif a.action == 'report':
        report(out)
    elif a.action in ('check', '_worker'):
        if not a.cell:
            p.error('--cell required')
        worker(out, a.cell, a.action == 'check')


if __name__ == '__main__':
    main()
