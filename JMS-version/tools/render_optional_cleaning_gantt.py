"""Read-only rendering of validated joint-model results; no optimization."""
from pathlib import Path
from collections import defaultdict
import argparse
import hashlib
import json
import math
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[2]
JOINT = ROOT/'JMS-version/joint_model'
sys.path.insert(0, str(JOINT))
from validate import validate, TOL

COLORS = {
    '产品取放': '#3977A8', '辅助取放': '#9572AD',
    '模块占用（含复位）': '#A5C9D0', '腔室装卸/旋转': '#84909B',
    '生产': '#D78251', '清洁': '#41836B',
}
LANES = ['ATR取放', 'VTR取放', 'AL占用', 'LL上槽1', 'LL上槽2',
         'LL下槽1', 'LL下槽2', 'CH1', 'CH2']


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def optimality_errors(data, physical):
    """Certify primary Cmax only; a fixed-structure optimum is insufficient."""
    errors = []
    if data.get('primary_status') != 'optimal':
        errors.append(f"primary_status={data.get('primary_status')}")
    if data.get('experiment_scope') != 'joint' or data.get('full_candidate_space') is not True:
        errors.append('not an unrestricted joint-model solve')
    if data.get('restricted_candidate_bounds') is not False:
        errors.append('candidate capacity is restricted or unspecified')
    if data.get('original_model_check') is not True or not physical.get('valid'):
        errors.append('validation failed')
    upper = physical.get('product_return_cmax')
    bound = data.get('primary_bound')
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and abs(v) < 1e19
               for v in (upper, bound)):
        errors.append('missing or sentinel primary bound')
    elif abs(upper-bound) > TOL:
        errors.append(f'primary bounds not closed: UB={upper}, LB={bound}')
    gap = data.get('primary_gap')
    if not isinstance(gap, (int, float)) or not math.isfinite(gap) or abs(gap) > 1e-6:
        errors.append(f'primary_gap={gap}')
    return errors


FLOW_COLORS = {
    'ATR持片（含取放/搬运/等待）': '#3977A8', 'AL驻留': '#9A78AC',
    'LL上层驻留': '#80B8BC', 'VTR持片（含取放/搬运/等待）': '#E3AD55',
    '腔内非加工驻留': '#CDD1D5', '加工': '#D78251', 'LL下层驻留': '#93B58C',
}


def wafer_rows(data):
    """Partition each product's saved loan interval; do not invent move times."""
    byjob = defaultdict(dict)
    for e in data['events']:
        if 'job' in e:
            byjob[e['job']][e['kind']] = e
    rows = []
    for j in sorted((j for j in data['jobs'] if j['product']), key=lambda j: j['name']):
        e = byjob[j['name']]
        ch_start, ch_end = j['load_end'], j['unload_start']
        segments = [
            (e['origin_pick']['start'], e['al_put']['end'], 'ATR持片（含取放/搬运/等待）'),
            (e['al_put']['end'], e['al_pick']['start'], 'AL驻留'),
            (e['al_pick']['start'], e['upper_put']['end'], 'ATR持片（含取放/搬运/等待）'),
            (e['upper_put']['end'], e['source_pick']['start'], 'LL上层驻留'),
            (e['source_pick']['start'], ch_start, 'VTR持片（含取放/搬运/等待）'),
        ]
        cursor = ch_start
        for c in sorted((c for c in data['cycles'] if j['pair'] in c['pairs']), key=lambda c: c['start']):
            if c['mode'] == 'clean' or c['start'] < cursor-TOL or c['end'] > ch_end+TOL:
                raise ValueError(f'Invalid product processing interval: {j["name"]}')
            segments.extend([(cursor, c['start'], '腔内非加工驻留'),
                             (c['start'], c['end'], '加工')])
            cursor = c['end']
        segments.extend([
            (cursor, ch_end, '腔内非加工驻留'),
            (ch_end, e['destination_put']['end'], 'VTR持片（含取放/搬运/等待）'),
            (e['destination_put']['end'], e['lower_pick']['start'], 'LL下层驻留'),
            (e['lower_pick']['start'], e['origin_put']['end'], 'ATR持片（含取放/搬运/等待）'),
        ])
        cursor = j['loan_start']
        for start, end, kind in segments:
            if abs(start-cursor) > TOL or end < start-TOL:
                raise ValueError(f'Discontinuous wafer timeline: {j["name"]}')
            if end > start:
                rows.append((j['name'], start, end, kind))
            cursor = end
        if abs(cursor-j['loan_end']) > TOL:
            raise ValueError(f'Incomplete wafer timeline: {j["name"]}')
    return rows


def draw_wafer_flow(data, output, stem, h, recipe, seed, certified):
    rows = wafer_rows(data)
    names = list(dict.fromkeys(row[0] for row in rows))
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.subplots_adjust(left=.12, right=.975, top=.85, bottom=.28)
    for name, start, end, kind in rows:
        ax.broken_barh([(start, end-start)], (names.index(name)-.34, .68),
                       facecolors=FLOW_COLORS[kind], edgecolors='none')
    ax.set_yticks(range(len(names)), names, fontsize=8)
    ax.set_ylim(len(names)-.5, -.7)
    ax.set_xlim(0, data['validation']['product_return_cmax']*1.015)
    ax.set_xlabel('时间 / s')
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E3E7EA', linewidth=.6)
    ax.spines[['top', 'right']].set_visible(False)
    label = 'Cmax全局最优（求解器容差内）' if certified else '可行排程，未证明最优'
    fig.suptitle(f"16片纯{recipe.replace('x', '×')}，H={h}：逐片连续状态", y=.97, fontsize=15)
    fig.text(.12, .90, f'{label} | 种子 {seed} | Cmax={data["validation"]["product_return_cmax"]:g} s', fontsize=10)
    legend = fig.legend(handles=[Patch(facecolor=v, label=k) for k, v in FLOW_COLORS.items()],
                        loc='lower center', bbox_to_anchor=(.52, .07), ncol=3,
                        frameon=False, fontsize=8)
    fig.text(.12, .035, '每行是一片产品晶圆，从首次取片到回片连续；取放交接归入机械手持片段。', fontsize=9)
    fig.text(.12, .01, '非加工驻留包含等待及旋转；本图不展示辅助片或末端清洁，不代表资源利用率或等待最优。', fontsize=9)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    if ax.xaxis.label.get_window_extent(renderer).overlaps(legend.get_window_extent(renderer)):
        raise ValueError('Wafer-flow legend overlaps the axis label')
    for ext in ('svg', 'png'):
        fig.savefig(output/f'{stem}_wafer_flow.{ext}', dpi=220, facecolor='white')
    plt.close(fig)
    return len(rows)


def chart_rows(data):
    """Use the same physical occupancy endpoints as the independent checker."""
    rows = []
    byjob = defaultdict(dict)
    jobs = {j['name']: j for j in data['jobs']}
    for e in data['events']:
        if 'job' in e:
            byjob[e['job']][e['kind']] = e
        if e['robot']:
            if 'job' in e:
                product = jobs[e['job']]['product']
            else:
                product = any(j['product'] and j['pair'] == e['pair'] for j in data['jobs'])
            rows.append((e['robot']+'取放', e['start'], e['end'],
                         '产品取放' if product else '辅助取放', e['name']))
        if e['location'].startswith('CH'):
            rows.append((e['location'], e['start'], e['end'], '腔室装卸/旋转', e['name']))
    slots = {'U': [], 'L': []}
    for name, es in byjob.items():
        if 'al_put' in es:
            rows.append(('AL占用', es['al_put']['start'], es['al_pick']['end'],
                         '模块占用（含复位）', name))
        if 'upper_put' in es:
            slots['U'].append((es['upper_put']['start'],
                               es['source_pick']['end']+data['config']['upper_reset'], name))
            slots['L'].append((es['destination_put']['start'],
                               es['lower_pick']['end']+data['config']['lower_reset'], name))
    # These equivalent slots are assigned for display, not claimed as saved
    # solver slot identities. Greedy interval coloring preserves capacity 2.
    for resource, intervals in slots.items():
        ends = [-float('inf'), -float('inf')]
        for start, end, name in sorted(intervals):
            slot = min(range(2), key=lambda i: ends[i])
            if ends[slot] > start + TOL:
                raise ValueError(f'Cannot display {resource}: occupancy exceeds two slots')
            ends[slot] = end
            lane = ('LL上槽' if resource == 'U' else 'LL下槽') + str(slot+1)
            rows.append((lane, start, end, '模块占用（含复位）', name))
    for c in data['cycles']:
        kind = '清洁' if c['mode'] == 'clean' else '生产'
        rows.append((f"CH{c['chamber']}", c['start'], c['end'], kind,
                     f"cycle_{c['chamber']}_{c['index']}"))
    # Simultaneous paired handling is one bar on the shared robot lane.
    return list(dict.fromkeys(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--require-optimal', action='store_true',
                        help='Refuse all output unless all four full-model primary bounds are closed')
    parser.add_argument('--wafer-flow', action='store_true',
                        help='Also draw continuous per-product state timelines')
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'JMS-version/figures'):
        parser.error('Output must be inside JMS-version/figures')
    if output == ROOT/'JMS-version/figures':
        parser.error('Use a separate figure subdirectory to preserve historical figures')
    spec = read(campaign/'campaign.json')
    selected = []
    for h in (3, 10):
        for recipe in ('4x1', '2x2'):
            cid = f'n16_H{h}_{recipe}_dual__s{args.seed}__joint'
            cell = next((c for c in spec['cells'] if c['id'] == cid), None)
            if cell is None:
                raise ValueError(f'Cell is absent: {cid}')
            folder = campaign/'runs'/cid
            evidence = read(folder/'evidence.json')
            result_path = folder/'result.json'
            if digest(result_path) != evidence['result_sha256']:
                raise ValueError(f'Result hash mismatch: {cid}')
            if not (evidence['complete'] and evidence['original_model_check']
                    and evidence['physical']['valid']):
                raise ValueError(f'Original acceptance failed: {cid}')
            data = read(result_path)
            if data.get('cleaning_policy') != 'optional_before_threshold':
                raise ValueError(f'Wrong cleaning policy: {cid}')
            config = read(campaign/'configs'/f"{cell['case']}.json")
            if data['config'] != config or digest(campaign/'configs'/f"{cell['case']}.json") != spec['case_hashes'][cell['case']]:
                raise ValueError(f'Configuration mismatch: {cid}')
            physical = validate(data)
            if not physical['valid']:
                raise ValueError(f'Physical replay failed: {cid}: {physical["errors"]}')
            errors = optimality_errors(data, physical)
            selected.append((cid, h, recipe, folder, data, physical, errors))
    if args.require_optimal:
        failed = [(cid, errors) for cid, _, _, _, _, _, errors in selected if errors]
        if failed:
            for cid, errors in failed:
                print('NOT CERTIFIED '+cid+': '+'; '.join(errors), file=sys.stderr)
            parser.exit(2, 'No optimal-paper figures written. Keep results; inspect bounds and solver logs.\n')
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
                         'axes.unicode_minus': False, 'svg.fonttype': 'none',
                         'font.size': 10})
    manifest = {
        'campaign': str(campaign), 'campaign_sha256': digest(campaign/'campaign.json'),
        'renderer_sha256': digest(Path(__file__)),
        'validator_sha256': digest(JOINT/'validate.py'),
        'seed_selection': 'Fixed seed supplied before plotting; no best-seed selection',
        'new_optimization_runs': 0, 'figures': [],
        'require_optimal': args.require_optimal,
        'scope': 'Primary Cmax optimality only if certified per figure; no waiting optimality claim',
        'display': 'Full timeline including terminal cleaning; dotted line marks product return makespan. '
                   'Robot lanes show explicit handling only, not inferred travel. LL slots are display interval colors.',
    }
    for cid, h, recipe, folder, data, physical, errors in selected:
        rows = chart_rows(data)
        cmax = physical['product_return_cmax']
        horizon = max(end for _, _, end, _, _ in rows)
        fig, ax = plt.subplots(figsize=(12, 6.2))
        fig.subplots_adjust(left=.105, right=.975, top=.80, bottom=.30)
        for lane, start, end, kind, _ in rows:
            if end-start <= 0:
                continue
            ax.broken_barh([(start, end-start)], (LANES.index(lane)-.31, .62),
                           facecolors=COLORS[kind], edgecolors='none')
        ax.set_yticks(range(len(LANES)), LANES)
        ax.set_ylim(len(LANES)-.5, -.8)
        ax.set_xlim(0, horizon*1.015)
        ax.set_xlabel('时间 / s')
        ax.set_axisbelow(True)
        ax.grid(axis='x', color='#E3E7EA', linewidth=.6)
        ax.spines[['top', 'right']].set_visible(False)
        ax.axvline(cmax, color='#333333', linestyle='--', linewidth=1)
        mode = recipe.replace('x', '×')
        fig.suptitle(f'现行清洁规则：16片纯{mode}，H={h}，双源', y=.965, fontsize=15)
        status_label = 'Cmax全局最优（求解器容差内）' if not errors else '可行排程（未证明最优）'
        fig.text(.105, .88,
                 f'种子 {args.seed} | {status_label} | 产品回片 Cmax = {cmax:g} s'
                 f" | 清洁次数 {physical['cleaning_count']}", fontsize=10)
        handles = [Patch(facecolor=color, label=label) for label, color in COLORS.items()]
        legend = fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.52, .10),
                            ncol=3, frameon=False, fontsize=10)
        fig.text(.105, .045, '完整时域含末端清洁；虚线为产品回片边界。机械手仅绘制显式取放，空白不等于全部空闲。', fontsize=9)
        fig.text(.105, .012, '模块占用含复位；LL等价槽位按区间着色展示，不代表求解器保存的槽号。', fontsize=9)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        if ax.xaxis.label.get_window_extent(renderer).overlaps(legend.get_window_extent(renderer)):
            raise ValueError('Figure layout overlaps: x-axis label and legend')
        stem = f'n16_H{h}_{recipe}_dual_s{args.seed}'
        for ext in ('svg', 'png'):
            fig.savefig(output/f'{stem}.{ext}', dpi=220, facecolor='white')
        plt.close(fig)
        flow_intervals = draw_wafer_flow(data, output, stem, h, recipe, args.seed, not errors) if args.wafer_flow else None
        manifest['figures'].append({
            'cell': cid, 'result': str(folder/'result.json'),
            'result_sha256': digest(folder/'result.json'),
            'evidence_sha256': digest(folder/'evidence.json'),
            'physical_recheck': physical, 'primary_status': data['primary_status'],
            'product_return_cmax': cmax, 'plot_horizon': horizon,
            'interval_count': len(rows), 'output_stem': stem,
            'primary_optimality_certified': not errors,
            'optimality_errors': errors, 'wafer_flow_intervals': flow_intervals,
        })
        print(f'RENDERED {cid}: Cmax={cmax:g}, full horizon={horizon:g}', flush=True)
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Four figures rendered; no solver run. Output: {output}', flush=True)


if __name__ == '__main__':
    main()
