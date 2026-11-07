"""Resource time lanes with wafer identity labels and complete wafer routes and audited timing completion.

Handling/rotation/processing timestamps are read from the verified solution.
Implicit robot travel is placed immediately before the next handling action;
alignment/pump/vent start immediately after deposit. These are explicit display
completions of minimum-lag constraints, not additional optimization results.
"""
from collections import defaultdict
import json
import math
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

STYLE = {
    'ATR取片': '#0F4D92', 'ATR放片': '#9A4D8E',
    '带片移动': '#5B8FD6', '承片等待': '#DBE8F5',
    'AL对准': '#C45AD6', 'LL抽气': '#4E8A65',
    'LL真空等待': '#AADCA9', 'LL放气': '#B86F6F',
    'LL大气等待': '#E4CCD8', 'VTR取放': '#E48B25',
    '腔室加工': '#B7413E', '腔内等待': '#F4CFCB',
    '腔室旋转': '#6E7595', '空载移动/复位': '#AAAAAA',
    '清洁': '#276741',
}
PATH_COLORS = ['#093B79', '#872196', '#007D65', '#976000', '#C93341', '#1A687C']
TOL = 2e-4


def demand(ok, message):
    if not ok:
        raise ValueError(message)


def build(d):
    cfg = d['config']
    events = d['events']
    jobs = sorted(d['jobs'], key=lambda j: (not j['product'], j.get('wafer_number', 0), j['name']))
    ej = defaultdict(dict)
    for e in events:
        if 'job' in e:
            ej[e['job']][e['kind']] = e
    bars, traces, completions = [], [], []
    slots, slot_ends = {}, {'U': [-math.inf] * 2, 'L': [-math.inf] * 2}

    def add(lane, start, end, action, origin='explicit', job=None):
        demand(end >= start - TOL, f'Negative state interval: {lane}/{action}')
        if end - start > 1e-6:
            bars.append(dict(lane=lane, start=start, end=end, action=action, origin=origin, job=job))

    # Each LL slot remains occupied until its pressure reset has completed.
    for key, put, pick, reset in [('U', 'upper_put', 'source_pick', cfg['upper_reset']),
                                  ('L', 'destination_put', 'lower_pick', cfg['lower_reset'])]:
        selected = [(ej[j['name']][put]['start'], j) for j in jobs if 'origin_pick' in ej[j['name']]]
        for _, j in sorted(selected, key=lambda x: (x[0], x[1]['name'])):
            e = ej[j['name']]
            idx = min(range(2), key=lambda i: slot_ends[key][i])
            demand(slot_ends[key][idx] <= e[put]['start'] + TOL, 'LL slots overlap')
            lane = ('上装载锁槽' if key == 'U' else '下装载锁槽') + str(idx + 1)
            slots[j['name'], key] = lane
            slot_ends[key][idx] = e[pick]['end'] + reset
            add(lane, e[put]['start'], e[put]['end'], 'ATR放片' if key == 'U' else 'VTR取放', job=j['name'])
            duration = cfg['pump'] if key == 'U' else cfg['vent']
            finish = e[put]['end'] + duration
            demand(finish <= e[pick]['start'] + TOL, 'Pressure change cannot finish before pickup')
            add(lane, e[put]['end'], finish, 'LL抽气' if key == 'U' else 'LL放气', 'earliest_completion', j['name'])
            completions.append(dict(lane=lane, start=e[put]['end'], end=finish, rule='pressure immediately after deposit'))
            add(lane, finish, e[pick]['start'], 'LL真空等待' if key == 'U' else 'LL大气等待', job=j['name'])
            add(lane, e[pick]['start'], e[pick]['end'], 'VTR取放' if key == 'U' else 'ATR取片', job=j['name'])
            add(lane, e[pick]['end'], e[pick]['end'] + reset, '空载移动/复位', 'model_reset', j['name'])

    # Paths use each wafer's real handoff times; no time is discarded.
    aux_index = 0
    for i, j in enumerate(jobs):
        e = ej[j['name']]
        if j['product']:
            short = 'W' + str(j['wafer_number'])
            desc = f"{short}={j.get('encoded_product', j['identity'])}"
        else:
            aux_index += 1
            short = f'A{aux_index}'
            desc = f"{short}=辅助片{j['identity']}"
        pts = []

        def point(time, lane):
            demand(not pts or time >= pts[-1][0] - TOL, 'Wafer path runs backwards')
            if not pts or pts[-1] != (time, lane):
                pts.append((time, lane))

        if 'origin_pick' in e:
            point(e['origin_pick']['start'], j['origin'])
            point(e['origin_pick']['end'], 'ATR机械手')
            if 'al_put' in e:
                point(e['al_put']['start'], 'ATR机械手'); point(e['al_put']['end'], '对准器 AL')
                point(e['al_pick']['start'], '对准器 AL'); point(e['al_pick']['end'], 'ATR机械手')
                add('对准器 AL', e['al_put']['start'], e['al_put']['end'], 'ATR放片', job=j['name'])
                finish = e['al_put']['end'] + cfg['alignment']
                demand(finish <= e['al_pick']['start'] + TOL, 'Alignment does not fit')
                add('对准器 AL', e['al_put']['end'], finish, 'AL对准', 'earliest_completion', j['name'])
                completions.append(dict(lane='对准器 AL', start=e['al_put']['end'], end=finish, rule='alignment immediately after deposit'))
                add('对准器 AL', finish, e['al_pick']['start'], 'LL大气等待', job=j['name'])
                add('对准器 AL', e['al_pick']['start'], e['al_pick']['end'], 'ATR取片', job=j['name'])
            point(e['upper_put']['start'], 'ATR机械手'); point(e['upper_put']['end'], slots[j['name'], 'U'])
            point(e['source_pick']['start'], slots[j['name'], 'U'])
        else:
            point(e['source_pick']['start'], j['origin'])
        point(e['source_pick']['end'], 'VTR机械手')
        point(j['load_start'], 'VTR机械手')
        chamber = next(e0['location'] for e0 in events if e0['kind'] == 'pair_load' and e0['pair'] == j['pair'])
        point(j['load_end'], '旋转腔 ' + chamber)
        point(j['unload_start'], '旋转腔 ' + chamber)
        point(j['unload_end'], 'VTR机械手')
        point(e['destination_put']['start'], 'VTR机械手')
        if 'origin_put' in e:
            point(e['destination_put']['end'], slots[j['name'], 'L'])
            point(e['lower_pick']['start'], slots[j['name'], 'L']); point(e['lower_pick']['end'], 'ATR机械手')
            point(e['origin_put']['start'], 'ATR机械手'); point(e['origin_put']['end'], j['origin'])
        else:
            point(e['destination_put']['end'], j['origin'])
        demand(abs(pts[0][0] - j['loan_start']) < TOL and abs(pts[-1][0] - j['loan_end']) < TOL, 'Incomplete loan trajectory')
        traces.append(dict(job=j['name'], label=short, description=desc, color=PATH_COLORS[i % len(PATH_COLORS)], points=pts))

    # Atomic robot actions plus a deterministic feasible placement of implicit
    # moves. Synchronous double picks are one resource action, not two conflicts.
    for robot in ['ATR', 'VTR']:
        action_groups = defaultdict(list)
        for e in events:
            if e['robot'] == robot:
                action_groups[e['start'], e['end'], e['location']].append(e)
        grouped = sorted(action_groups.items())
        held = set()
        prev = None
        for (start, end, location), group in grouped:
            lane = robot + '机械手'
            if prev:
                prev_end, prev_location = prev
                demand(start >= prev_end - TOL, 'Robot atomic actions overlap')
                travel = 0 if location == prev_location or {location, prev_location} <= {'U', 'L'} else cfg['atr_travel' if robot == 'ATR' else 'vtr_travel']
                if robot == 'ATR' and prev_location in ('U', 'L') and (location.startswith('LP') or location == 'AS') and any(e['kind'] == 'origin_pick' for e in group):
                    travel = cfg['atr_empty_ll_to_lp']
                depart = start - travel
                demand(depart >= prev_end - TOL, 'Implicit robot travel does not fit')
                if held:
                    add(lane, prev_end, depart, '承片等待', 'completed_robot_state')
                add(lane, depart, start, '带片移动' if held else '空载移动/复位', 'latest_travel')
                if travel:
                    completions.append(dict(lane=lane, start=depart, end=start, origin=prev_location, destination=location, held=sorted(held), rule='travel immediately before next handling'))
            kinds = {e['kind'] for e in group}
            pick_kinds = {'origin_pick', 'al_pick', 'source_pick', 'lower_pick', 'pair_unload'}
            add(lane, start, end, ('ATR取片' if kinds <= pick_kinds else 'ATR放片') if robot == 'ATR' else 'VTR取放')
            for e in group:
                names = [e['job']] if 'job' in e else [j['name'] for j in jobs if j['pair'] == e.get('pair')]
                if e['kind'] in pick_kinds:
                    held.update(names)
                else:
                    demand(set(names) <= held, 'Robot places wafer it does not hold')
                    held.difference_update(names)
            prev = end, location
        demand(not held, 'Robot retains wafers at end of display')

    # Partition the chamber union into mutually exclusive states. Two pairs
    # inside the same four-position chamber are not counted as two resources.
    for ch in cfg['chambers']:
        location = f'CH{ch}'
        acts = [e for e in events if e['location'] == location]
        cycles = [c for c in d['cycles'] if c['chamber'] == ch]
        occupancy = [(j['load_start'], j['unload_end']) for j in jobs if any(e['kind'] == 'pair_load' and e.get('pair') == j['pair'] for e in acts)]
        bounds = sorted({t for a, b in occupancy for t in (a, b)} | {e[k] for e in acts for k in ('start', 'end')} | {c[k] for c in cycles for k in ('start', 'end')})
        for a, b in zip(bounds, bounds[1:]):
            t = (a + b) / 2
            c = next((c for c in cycles if c['start'] <= t < c['end']), None)
            e = next((e for e in acts if e['start'] <= t < e['end']), None)
            if c:
                kind = '清洁' if c['mode'] == 'clean' else '腔室加工'
            elif e:
                kind = '腔室旋转' if e['kind'] == 'rotate' else 'VTR取放'
            elif any(s <= t < f for s, f in occupancy):
                kind = '腔内等待'
            else:
                continue
            add('旋转腔 ' + location, a, b, kind)

    origins = list(dict.fromkeys(j['origin'] for j in jobs if j['origin'] not in ('VS',)))
    lanes = origins + ['ATR机械手', '对准器 AL', '上装载锁槽1', '上装载锁槽2', 'VTR机械手']
    lanes += ['旋转腔 CH' + str(c) for c in cfg['chambers']]
    lanes += ['下装载锁槽1', '下装载锁槽2']
    if any(j['origin'] == 'VS' for j in jobs):
        lanes += ['VS']
    origin_actions = set()
    for e in events:
        if e['location'] in origins or e['location'] == 'VS':
            kind = ('ATR取片' if e['kind'] == 'origin_pick' else 'ATR放片') if e['robot'] == 'ATR' else 'VTR取放'
            origin_actions.add((e['location'], e['start'], e['end'], kind))
    for lane, start, end, kind in sorted(origin_actions):
        add(lane, start, end, kind)
    # Check every explicit event is represented on its owning resource lane.
    for e in events:
        lane = e['robot'] + '机械手' if e['robot'] else '旋转腔 ' + e['location']
        cover = sum(max(0, min(e['end'], b['end']) - max(e['start'], b['start'])) for b in bars if b['lane'] == lane)
        demand(abs(cover - (e['end'] - e['start'])) < TOL, 'Uncovered or duplicated explicit action ' + e['name'])
    for lane in lanes:
        ordered = sorted((b for b in bars if b['lane'] == lane), key=lambda b: b['start'])
        for a, b in zip(ordered, ordered[1:]):
            demand(a['end'] <= b['start'] + TOL, 'Display resource states overlap: ' + lane)
    return lanes, bars, traces, completions


def draw(d, physical, certified, dest):
    lanes, bars, traces, completions = build(d)
    plt.rcParams.update({'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'], 'axes.unicode_minus': False, 'pdf.fonttype': 42, 'font.size': 13})
    fig, ax = plt.subplots(figsize=(10.5, 8.5))
    fig.subplots_adjust(left=.18, right=.975, top=.87, bottom=.30)
    horizon = max(b['end'] for b in bars)
    cmax = physical['product_return_cmax']
    pos = {lane: i for i, lane in enumerate(lanes)}
    for i in range(len(lanes)):
        ax.axhspan(i - .45, i + .45, color='#F7F8FA' if i % 2 == 0 else 'white', zorder=0)
        ax.axhline(i + .5, color='#DFE2E6', lw=.45, zorder=0)
    for b in bars:
        ax.broken_barh([(b['start'], b['end'] - b['start'])], (pos[b['lane']] - .34, .68), facecolors=STYLE[b['action']], edgecolors='white', linewidth=.25, zorder=2)
    label_groups = defaultdict(list)
    for t in traces:
        for (start, lane), (end, next_lane) in zip(t['points'], t['points'][1:]):
            if lane == next_lane and not lane.startswith('旋转腔') and end - start >= max(18, horizon * .05):
                label_groups[lane, start, end].append(t['label'])
    for (lane, start, end), ids in label_groups.items():
        ax.text((start + end) / 2, pos[lane], ' / '.join(ids), color='#222222', fontsize=10.5, ha='center', va='center', zorder=7, bbox=dict(facecolor='white', edgecolor='none', alpha=.92, pad=.6))
    names = {t['job']: t['label'] for t in traces}
    for cycle in d['cycles']:
        ids = [names[j['name']] for j in d['jobs'] if j['pair'] in cycle['pairs']]
        title = ('清洁' if cycle['mode'] == 'clean' else cycle['mode'].replace('x', '×')) + ' | ' + '/'.join(ids)
        ax.text((cycle['start'] + cycle['end']) / 2, pos['旋转腔 CH' + str(cycle['chamber'])], title, color='white', fontsize=10.5, ha='center', va='center', zorder=7)
    endpoint_ids = defaultdict(list)
    for t in traces:
        for point in (t['points'][0], t['points'][-1]):
            endpoint_ids[point].append(t['label'])
    for (time, lane), ids in endpoint_ids.items():
        at_start = time < horizon / 2
        ax.text(time + (4 if at_start else -4), pos[lane], '/'.join(ids), ha='left' if at_start else 'right', va='center', fontsize=10.5, color='#333333', zorder=7)
    labels = [('真空辅助库 VS' if x == 'VS' else '产品起点/终点 ' + x if x.startswith('LP') else x) for x in lanes]
    ax.set_yticks(range(len(lanes)), labels)
    ax.set_ylim(len(lanes) - .5, -.6); ax.set_xlim(-2, horizon + max(10, horizon * .025))
    ax.set_xlabel('时间 / s', labelpad=8)
    ax.set_xticks(sorted(set(list(range(0, int(horizon) + 1, 50)) + [cmax, horizon])))
    ax.tick_params(axis='x', labelsize=11)
    ax.grid(axis='x', color='#E0E3E8', lw=.55); ax.set_axisbelow(True)
    ax.tick_params(axis='y', length=0, pad=8)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.axvline(cmax, color='#222222', ls='--', lw=1, zorder=3)
    ax.axvline(horizon, color='#777777', ls=':', lw=1, zorder=3)
    status = '产品完工时间已证最优' if certified else '可行排程，未证明最优'
    fig.suptitle(f'{status}：Cmax = {cmax:g} s；全部占用结束 {horizon:g} s', y=.978, fontsize=18)
    fig.text(.56, .916, '色块：模块动作及状态　　色块内编号：晶圆身份', ha='center', fontsize=13)
    used = {b['action'] for b in bars}
    action_handles = [Patch(facecolor=c, label=k) for k, c in STYLE.items() if k in used]
    fig.legend(handles=action_handles, loc='lower center', bbox_to_anchor=(.55, .085), ncol=5, frameon=False, fontsize=12, columnspacing=1.4)
    fig.legend(handles=[Patch(facecolor='none', edgecolor='none', label=t['description']) for t in traces], loc='lower center', bbox_to_anchor=(.55, .047), ncol=min(4, len(traces)), frameon=False, fontsize=12)
    fig.text(.55, .022, '隐式动作按可行时序补全：搬运紧接下一取放前；对准、抽气及放气紧接放片后。槽号为等价显示分配。', ha='center', fontsize=10.5, color='#444444')
    stem = 'fig_current_defaults_gantt_cn'
    for ext in ['pdf', 'png', 'svg']:
        fig.savefig(dest / (stem + '.' + ext), dpi=220, facecolor='white')
    plt.close(fig)
    evidence = dict(lanes=lanes, bars=bars, paths=traces, implicit_action_completions=completions, explicit_events_covered=len(d['events']), complete_wafer_paths=len(traces), overlapping_display_states=0, optimization_calls=0)
    (dest / 'swimlane_actions.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    return horizon, evidence
