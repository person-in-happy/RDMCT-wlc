"""Retiming manuscript structures for upper bounds only, never global proof."""
from pathlib import Path
from dataclasses import replace, asdict
from itertools import combinations
import argparse
import copy
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'JMS-version/joint_model'))
from model import Config, Integrated
from reuse_legacy import convert
from seed import construct, constrain_seed
from run_experiments import fix_structure, digest, dump, finite, assets
from validate import validate, TOL
from grippers import attach_hands, HANDS


def source_path(h, recipe):
    b = ROOT/'JMS-version/results/wafer_multiscale_gantt'
    if recipe == '4x1':
        folder = b/('3xclean/gantt' if h == 3 else 'gantt')/f'wafer16_41_clean{h}_20260826'
        return folder/f'wafer16_41_clean{h}_20260826_validated_solutions.json'
    folder = 'wafer16_22_clean3_productcmax_20260903' if h == 3 else 'wafer16_22_clean10'
    return b/'gantt_cycle_mapping_20260907'/folder/'validated_solutions.json'


def remap_chambers(data, cfg):
    data = copy.deepcopy(data)
    mapping = {2: 1, 3: 2}
    data['config'] = asdict(cfg)
    for p in data['pairs']:
        p['chamber'] = mapping[p['chamber']]
    for c in data['cycles']:
        c['chamber'] = mapping[c['chamber']]
    for e in data['events']:
        if e['location'].startswith('CH'):
            e['location'] = 'CH'+str(mapping[int(e['location'][2:])])
        if 'chamber' in e:
            old = e['chamber']; e['chamber'] = mapping[old]
            e['name'] = e['name'].replace(f'_{old}_', f'_{mapping[old]}_', 1)
    return data


def run(args):
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'runner_snapshot.py').write_bytes(Path(__file__).read_bytes())
    cfg_path = ROOT/'JMS-version/results/paper_gantt_n16_optimal_attempt_20261020/configs'/f'{args.case}.json'
    cfg = Config(**json.loads(cfg_path.read_text(encoding='utf-8-sig')))
    mode = '4x1' if '_4x1_' in args.case else '2x2'
    source = source_path(cfg.cleaning_interval, mode)
    record = json.loads(source.read_text(encoding='utf-8-sig'))[0]
    old = remap_chambers(convert(record, source, replace(cfg, chambers=(2, 3))), cfg)
    old_hands = attach_hands(old)
    old['validation'] = validate(old)
    dump(out/'legacy_reconstruction.json', old)
    serial = construct(cfg, old)
    dump(out/'serial_schedule.json', serial)
    compact = replace(cfg, max_pairs=len(serial['pairs']),
                      max_cycles=max(c['index'] for c in serial['cycles'])+1)
    dump(out/'manifest.json', dict(case=args.case, source=str(source), source_sha256=digest(source),
         config_sha256=digest(cfg_path), assets=assets(), script_sha256=digest(Path(__file__)),
         scope='Fixed manuscript structure; feasible upper bounds only; NOT unrestricted optimum',
         time_limit=args.time_limit, config=asdict(cfg), compact_config=asdict(compact)))
    print(f'BUILD {args.case}: manuscript Cmax={old["cmax"]:g}; serial completion={serial["cmax"]:g}', flush=True)
    x = Integrated(compact); m = x.model
    m.hideOutput(False)
    m.setIntParam('parallel/maxnthreads', 1)
    # Keep large-M feasibility residuals below the independent replay tolerance.
    m.setRealParam('numerics/feastol', 1e-10)
    m.setRealParam('limits/memory', 6000)
    m.setLogfile(str(out/'solver.log'))
    fix_structure(x, serial)
    fix = constrain_seed(x, serial)
    m.setObjective(0, 'minimize'); m.setRealParam('limits/time', 30)
    m.optimize()
    if not m.getNSols():
        raise RuntimeError('Serial material completion failed')
    solution = m.getBestSol()
    initial = {v.name: m.getSolVal(solution, v) for v in m.getVars(transformed=False)}
    m.freeTransform()
    for v, lb, ub in fix:
        m.chgVarLb(v, lb); m.chgVarUb(v, ub)
    m.setObjective(x.primary_objective, 'minimize')
    events = {e['name']: e for e in old['events']}
    variable = {v.name: v for v in m.getVars(transformed=False)}
    old_order = []
    def fix_reference(v, value):
        old_order.append((v, v.getLbOriginal(), v.getUbOriginal()))
        m.chgVarLb(v, value); m.chgVarUb(v, value)
    for robot_events in x.robots.values():
        for a, b in combinations(robot_events, 2):
            if a['name'] not in events or b['name'] not in events:
                continue
            ea, eb = events[a['name']], events[b['name']]
            # Simultaneous handling stays free; otherwise keep the reference order.
            if ea['end'] <= eb['start']+TOL:
                value = 1
            elif eb['end'] <= ea['start']+TOL:
                value = 0
            else:
                continue
            v = variable['order_'+a['name']+'_'+b['name']]
            fix_reference(v, value)
            sync_name = 'sync_'+a['name']+'_'+b['name']
            if sync_name in variable:
                fix_reference(variable[sync_name], 0)
    # Retain reference interval order as well as handling order. These are
    # warm-start-only restrictions and are all released in the next stage.
    byjob = {}
    for e in old['events']:
        if 'job' in e:
            byjob.setdefault(e['job'], {})[e['kind']] = e
    starts = {}
    for j in old['jobs']:
        name = j['name']; e = byjob[name]
        starts['VTR_hand', name+'_in'] = e['source_pick']['start']
        starts['VTR_hand', name+'_out'] = j['unload_start']
        if 'al_put' in e:
            starts['AL', name] = e['al_put']['start']
        if 'upper_put' in e:
            starts['U', name] = e['upper_put']['start']
            starts['L', name] = e['destination_put']['start']
        if old_hands:
            for leg in ('in', 'out'):
                for slot, hand in enumerate(HANDS):
                    vn = f'slot_VTR_hand_{name}_{leg}_{slot}'
                    if vn in variable:
                        fix_reference(variable[vn], int(j['vtr_hand_'+leg] == hand))
    for resource, intervals in x.intervals.items():
        if resource == 'ATR_hand':
            continue
        for a, b in combinations(intervals, 2):
            ki, kj = a[0], b[0]
            vn = f'order_{resource}_{ki}_{kj}'
            if vn in variable and (resource, ki) in starts and (resource, kj) in starts:
                fix_reference(variable[vn], int(starts[resource, ki] <= starts[resource, kj]))
    loans = {j['name'].removeprefix('aux_'): j['loan_start'] for j in old['jobs'] if not j['product']}
    for (ki, kj), v in x.dummy_orders.items():
        if ki in loans and kj in loans:
            fix_reference(v, int(loans[ki] <= loans[kj]))
    m.setRealParam('limits/time', min(60, args.time_limit))
    print('RETIME manuscript handling order under current constraints', flush=True)
    m.optimize()
    stages = [dict(stage='manuscript_order', status=str(m.getStatus()), seconds=m.getSolvingTime())]
    incumbent = initial
    if m.getNSols():
        solution = m.getBestSol()
        incumbent = {v.name: m.getSolVal(solution, v) for v in m.getVars(transformed=False)}
        stages[-1]['cmax'] = m.getSolVal(solution, x.cmax)
    m.freeTransform()
    for v, lb, ub in old_order:
        m.chgVarLb(v, lb); m.chgVarUb(v, ub)
    sol = m.createSol()
    for v in m.getVars(transformed=False):
        m.setSolVal(sol, v, incumbent[v.name])
    if not m.checkSol(sol, printreason=False, completely=True):
        raise RuntimeError('Retimed start rejected after releasing robot orders')
    m.addSol(sol)
    print('IMPROVE all timing/resource orders; manuscript pairing and chamber cycles remain fixed', flush=True)
    m.setRealParam('limits/time', args.time_limit)
    m.optimize()
    stages.append(dict(stage='fixed_structure', status=str(m.getStatus()), seconds=m.getSolvingTime()))
    result = x.result()
    result['config'] = asdict(cfg)
    result['validation'] = validate(result)
    result['original_model_check'] = bool(m.getNSols() and m.checkSol(m.getBestSol(), printreason=False, completely=True))
    result.update(experiment_scope='manuscript_structure_upper_bound', full_candidate_space=False,
                  primary_status='not_certified', primary_bound=None, primary_gap=None,
                  global_optimality_claim=False, legacy_reuse=old['legacy_reuse'])
    result['conditional_bound'] = result.pop('dual_bound', None)
    result['conditional_gap'] = result.pop('gap', None)
    dump(out/'result.json', finite(result)); dump(out/'stages.json', finite(stages))
    if not result['validation']['valid'] or not result['original_model_check']:
        raise RuntimeError('Warm candidate failed validation')
    solution = m.getBestSol()
    dump(out/'variables.json', dict(values={v.name: m.getSolVal(solution, v) for v in m.getVars(transformed=False)}))
    print(f'VALIDATED UPPER BOUND {args.case}: {result["cmax"]:g}; NOT global proof', flush=True)
    m.freeProb()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--case', required=True, choices=[f'n16_H{h}_{r}_dual' for h in (3, 10) for r in ('4x1', '2x2')])
    parser.add_argument('--output', required=True)
    parser.add_argument('--time-limit', type=float, default=300)
    args = parser.parse_args()
    if args.time_limit <= 0:
        parser.error('Positive warm-start subproblem time required')
    run(args)
