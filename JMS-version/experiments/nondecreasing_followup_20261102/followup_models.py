"""Independent review follow-ups; no changes to historical solver code."""
from pathlib import Path
from collections import defaultdict
from dataclasses import asdict, replace
import csv
import gc
import json
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKEND = ROOT / 'JMS-version/model4_pjob_nondecreasing_20261102'
STRENGTH = HERE.parent / 'nondecreasing_strengthening_20261102'
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(STRENGTH))
from strengthen_models import (backend, scip, REAL_MODEL, WaferModel, encoding,
    groups_from_config, dimensions, lift_start, assignment_solution, assert_wafer_decode, audit_full)
from run_experiments import dump, finite, digest, ports, solve, incumbent_checks
from revalidate import read
from validate import validate
from seed import construct
from reference_completion import complete_reference
from review_experiments import physical_metrics

RESULTS = ROOT / 'JMS-version/results'
CROSS = RESULTS / 'pjob_fifo_crossover_all_20261030_190540'
PAPER = RESULTS / 'pjob_fifo_paper_all_20261030_075555'
SUITES = ('timing', 'parallel', 'exact', 'residency')


def plan(suite, repeats=6):
    cells = []
    if suite == 'timing':
        for n in (8, 16):
            for recipe in ('4x1', '2x2', 'mixed'):
                case = f'n{n}_H5_{recipe}_dual'
                ref = CROSS / 'references' / case
                for repeat in range(1, repeats + 1):
                    for arm in (('pjob', 'wafer') if repeat % 2 else ('wafer', 'pjob')):
                        cells.append(dict(id=f'{case}__r{repeat}__{arm}', case=case, arm=arm,
                            kind='timing', repeat=repeat, source=str(ref / 'reference.json'), values=str(ref / 'common.json')))
    elif suite == 'parallel':
        for recipe, duration, threshold in (('4x1', 180, 3), ('4x1', 600, 3), ('2x2', 90, 2)):
            cfg = backend.Config(load_ports=ports(2, recipe),
                pjobs=[dict(id=f'Pjob{i}', mode=recipe, chambers=[i + 1], wafers=[f'LP{i}_W1']) for i in (1, 2)],
                cleaning_interval=threshold, full_time=duration if recipe == '4x1' else 180,
                mix_time=duration if recipe == '2x2' else 90)
            case = f'n2_{recipe}_t{duration}_H{threshold}_qualified'
            cells.append(dict(id=case, case=case, kind='parallel', arm='pjob', config=asdict(cfg), seed=1))
    elif suite == 'exact':
        for n, recipe, h in ((1, '4x1', 3), (1, '2x2', 2), (2, '4x1', 3),
                             (2, '2x2', 2), (2, 'mixed', 3), (4, 'mixed', 3)):
            case = f'n{n}_H{h}_{recipe}_dual'
            cfg = backend.Config(load_ports=ports(n, recipe), cleaning_interval=h)
            cells.append(dict(id=case + '__reference', case=case, kind='reference', arm='pjob', config=asdict(cfg)))
            for arm in ('pjob', 'wafer'):
                cells.append(dict(id=case + '__' + arm, case=case, kind='exact', arm=arm, config=asdict(cfg), seed=1))
        # Exercise the newly permitted same-Pjob, same-LP paired pickup explicitly.
        for recipe, h in (('4x1', 3), ('2x2', 2)):
            case = f'n2_H{h}_{recipe}_dual_same_lp'
            lp = ports(2, recipe)
            for inventory in lp.values():
                for mode in inventory: inventory[mode] = 0
            lp['LP1'][recipe] = 2
            cfg = backend.Config(load_ports=lp, cleaning_interval=h)
            cells.append(dict(id=case + '__reference', case=case, kind='reference', arm='pjob', config=asdict(cfg)))
            for arm in ('pjob', 'wafer'):
                cells.append(dict(id=case + '__' + arm, case=case, kind='exact', arm=arm, config=asdict(cfg), seed=1))
    elif suite == 'residency':
        for source in ('single', 'dual'):
            case = f'n4_H10_mixed_{source}'
            ref = PAPER / 'references' / case
            for limit in (10000, 500, 250):
                cells.append(dict(id=f'{case}__R{limit}', case=case, kind='residency', arm='fixed_refined',
                    limit=limit, seed=1, source=str(ref / 'reference.json'), values=str(ref / 'common.json')))
    else:
        raise ValueError(suite)
    return cells


def build_fair(cfg, arm):
    """Same constructor statistics in both arms; final statistics outside timing.

    The extra wafer-only dimensions() traversal in the old entry is omitted.
    Mathematical constraints are identical to that entry.
    """
    old = scip.Model
    try:
        if arm == 'wafer':
            groups = groups_from_config(cfg)
            n = sum(g.count for g in groups)
            scip.Model = lambda *a, **k: WaferModel(*a, groups=groups, product_bound=min(n, cfg.max_pairs or n), **k)
        x = backend.Integrated(cfg)
    finally:
        scip.Model = old
    if arm == 'wafer':
        m = x.model
        codes = encoding(cfg)
        x.wafer_pickup = {w: m.addVar(lb=0, ub=x.H, name='wafer_pickup_' + w) for w in codes}
        tasks = defaultdict(list)
        for w, code in codes.items():
            tasks[code['pjob']].append(w)
            m.addCons(scip.quicksum(y for (label, _, _), y in m.wafer_selectors.items() if label == w) == 1)
            for p in range(min(x.N, x.P)):
                for r in (0, 1):
                    x.eq(x.wafer_pickup[w], x.jobs[f'prod_{p}_{r}']['first']['s'], m.wafer_selectors[w, p, r])
        for labels in tasks.values():
            labels.sort(key=lambda w: codes[w]['pjob_index'])
            for a, b in zip(labels, labels[1:]):
                m.addCons(x.wafer_pickup[b] >= x.wafer_pickup[a] )
    return x


def overlap_constraints(x):
    """A positive overlap of the first production cycles is a witness target."""
    cfg = x.cfg
    recipe = next(mode for mode, count in cfg.load_ports['LP1'].items() if count)
    for chamber in (2, 3):
        x.model.addCons(x.cy.kind[chamber, 0, recipe] == 1)
    x.model.addCons(x.cy.end[2, 0] >= x.cy.start[3, 0] + 1)
    x.model.addCons(x.cy.end[3, 0] >= x.cy.start[2, 0] + 1)


def numbers(d):
    report = physical_metrics(d)
    ps = [j for j in d['jobs'] if j['product']]
    report.update(product_flow_sum=sum(j['loan_end'] - j['loan_start'] for j in ps),
        product_chamber_sum=sum(j['unload_start'] - j['load_end'] for j in ps),
        product_pick_sum=sum(j['loan_start'] for j in ps), product_return_sum=sum(j['loan_end'] for j in ps))
    return report


def export_events(dest, data):
    for name in ('events', 'cycles', 'jobs'):
        rows = data[name]
        with (dest / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=sorted(set().union(*(r.keys() for r in rows))))
            writer.writeheader()
            writer.writerows(rows)


def save_assignment(x, sol):
    values = {v.name: x.model.getSolVal(sol, v) for v in x.model.getVars(transformed=False)}
    if isinstance(x.model, WaferModel):
        values.update({name: x.model.getSolVal(sol, expression) for name, expression in x.model.aggregate_selectors.items()})
    return values


def finite_bound(value):
    return float(value) if value is not None and abs(value) < 1e19 else None


def run_cell(cell, dest, settings, campaign):
    kind = cell['kind']
    if kind == 'reference':
        cfg = backend.Config(**cell['config'])
        x = backend.Integrated(cfg)
        begin = time.perf_counter()
        try:
            schedule = construct(cfg, balanced=True)
            factory = scip.Model
            def reference_model(*args, **kwargs):
                m = factory(*args, **kwargs)
                m.setIntParam('parallel/maxnthreads', 1)
                m.setLogfile(str(dest / 'reference_solver.log'))
                return m
            scip.Model = reference_model
            try:
                serial, common, levels, completion = complete_reference(x, schedule, settings['memory_mb'], spbs_budget=0)
            finally:
                scip.Model = factory
            sol = assignment_solution(x, common)
            reference = x.result(solution=sol)
            x.model.freeSol(sol)
            assert validate(reference)['valid']
            dump(dest / 'result.json', reference)
            dump(dest / 'variables.json', dict(values=common))
            return dict(state='reference_checked', valid=True, target_met=True, complete=True,
                preparation_seconds=time.perf_counter() - begin, completion=completion,
                metrics=numbers(reference), solver_started=True, scope='shared_reference_completion_only')
        finally:
            x.model.freeProb()
    if kind == 'residency':
        source = read(cell['source'])
        cfg = backend.Config(**source['config'])
        cfg = replace(cfg, module_residency=cell['limit'], robot_residency=cell['limit'])
        config = dest / 'config.json'
        dump(config, asdict(cfg))
        solve(config, dest / 'solve', time_limit=settings['time_limit'], stage2_limit=settings['stage2_limit'],
            seed=cell['seed'], warm_start=cell['values'], fixed=cell['source'], memory_mb=settings['memory_mb'],
            initialization='none', cut_profile='standard')
        data = read(dest / 'solve/result.json')
        first = read(dest / 'solve/phase1.json')
        valid = bool(data.get('result_eligible'))
        record = dict(complete=True, valid=valid, target_met=valid, state=data['status'],
            scope='same_fixed_pairing_chamber_cycles_under_residency_limits',
            primary_state=first['status'], primary_lower_bound=finite_bound(first['dual_bound']),
            primary_solve_seconds=first['solve_seconds'], solver_started=True)
        if valid:
            values = read(dest / 'solve/variables.json')['values']
            record['full_model_audit'] = audit_full(cfg, values, data)
            dump(dest / 'variables.json', dict(values=values))
            record.update(metrics=numbers(data), primary_metrics=numbers(first))
            export_events(dest, data)
        dump(dest / 'result.json', data)
        return finite(record)

    source = values = None
    if kind == 'timing':
        source, values = read(cell['source']), read(cell['values'])['values']
        cfg = backend.Config(**source['config'])
    elif kind == 'exact':
        ref = campaign / 'runs' / (cell['case'] + '__reference')
        ev = read(ref / 'evidence.json')
        for name in ('result.json', 'variables.json'):
            if digest(ref / name) != ev['output_hashes'][name]:
                raise RuntimeError('Shared reference changed: ' + str(ref))
        source, values = read(ref / 'result.json'), read(ref / 'variables.json')['values']
        cfg = backend.Config(**cell['config'])
    else:
        cfg = backend.Config(**cell['config'])
    begin = time.perf_counter()
    x = build_fair(cfg, cell['arm'])
    build_seconds = time.perf_counter() - begin
    m = x.model
    try:
        warm_values = None
        begin = time.perf_counter()
        if source is not None:
            # lift_start includes the same canonicalization and original check in both arms.
            warm_values = lift_start(x, cell['arm'], source, values)
        map_check_seconds = time.perf_counter() - begin
        # This final reporting scan is outside both reported timing components.
        x.original_dimensions = dimensions(x)
        if kind == 'parallel':
            overlap_constraints(x)
        record = dict(complete=True, arm=cell['arm'], build_seconds=build_seconds,
            mapping_and_check_seconds=map_check_seconds, preparation_seconds=build_seconds + map_check_seconds,
            dimensions=x.original_dimensions, full_candidate_space=not x.bounded,
            reporting_scan_in_timed_region=False, common_constructor_statistics_passes=1,
            scope='membership_only_same_nondecreasing_release' if kind in ('timing', 'exact') else 'positive_overlap_witness_domain')
        if source is not None:
            record['source_cmax'] = source['cmax']
            record['shared_source_sha256'] = digest(Path(cell['source'])) if kind == 'timing' else ev['output_hashes']['result.json']
        if kind == 'timing':
            sol = assignment_solution(x, warm_values)
            data = x.result(solution=sol)
            assert_wafer_decode(x, sol, data)
            assert validate(data)['valid']
            m.freeSol(sol)
            record.update(state='checked_without_optimization', valid=True, target_met=True,
                          solver_started=False, metrics=numbers(data))
            dump(dest / 'result.json', data)
            return record
        m.setIntParam('parallel/maxnthreads', 1)
        m.setIntParam('randomization/randomseedshift', cell['seed'])
        m.setRealParam('limits/time', settings['time_limit'])
        m.setRealParam('limits/memory', settings['memory_mb'])
        m.setLogfile(str(dest / 'solver.log'))
        m.setObjective(x.cmax, 'minimize')
        if warm_values is not None:
            m.addSol(assignment_solution(x, warm_values))
        m.optimize()
        record.update(state=str(m.getStatus()), solver_started=True, solve_seconds=m.getSolvingTime(),
            lower_bound=finite_bound(m.getDualbound()), gap=finite_bound(m.getGap()), nodes=m.getNNodes(),
            valid=False, target_met=False)
        data = x.result()
        if m.getNSols():
            checks = incumbent_checks(m)
            assert checks['original_model_check'] and validate(data)['valid']
            assert_wafer_decode(x, m.getBestSol(), data)
            full_values = save_assignment(x, m.getBestSol())
            data.update(checks, validation=validate(data))
            record.update(valid=True, metrics=numbers(data), upper_bound=data['cmax'],
                target_met=(record['state'] == 'optimal') if kind == 'exact' else numbers(data)['production_overlap'] > 1e-4)
            dump(dest / 'variables.json', dict(values=full_values))
            export_events(dest, data)
        dump(dest / 'result.json', finite(data))
    finally:
        m.freeProb()
    del x, m
    gc.collect()
    if record['valid']:
        record['full_model_audit'] = audit_full(cfg, full_values, data)
        dump(dest / 'full_model_audit.json', record['full_model_audit'])
    return finite(record)
