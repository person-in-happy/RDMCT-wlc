"""Pjob product-index encoding and strictly ordered LP release.

Product identities are input/output metadata. The MILP uses inventory selectors,
one continuous boundary per adjacent occupied LP, and existing ATR order bits.
"""
from collections import defaultdict
from pjobs import groups_from_config


def encoding(cfg):
    tasks = defaultdict(list)
    for group in groups_from_config(cfg):
        for label in group.labels:
            number = 25 * (group.load_port - 1) + int(label.split('_W')[1])
            tasks[group.pjob].append((number, label, group.load_port))
    return {label: dict(pjob=task, pjob_index=k, encoded_product=f'{task}[{k}]',
                       wafer_number=number, load_port=lp)
            for task, products in sorted(tasks.items())
            for k, (number, label, lp) in enumerate(sorted(products), 1)}


def add_release_boundaries(x):
    bytask = defaultdict(list)
    for group in x.groups:
        bytask[group.pjob].append(group)
    x.release_boundaries = {}
    for task, groups in sorted(bytask.items()):
        groups.sort(key=lambda g: g.load_port)
        for left, right in zip(groups, groups[1:]):
            boundary = x.cont(f'pjob_release_boundary_{task}_{left.load_port}')
            x.release_boundaries[task, left.load_port] = boundary
            for p in range(min(x.N, x.P)):
                for r in (0, 1):
                    event = x.jobs[f'prod_{p}_{r}']['first']
                    a = x.pair.member[left.identifier, p, r]
                    b = x.pair.member[right.identifier, p, r]
                    x.model.addCons(event['e'] <= boundary + x.M * (1 - a))
                    x.model.addCons(event['s'] >= boundary - x.M * (1 - b))


def decode_members(x, value):
    """Decode the solved release order using the input's global Pjob indices."""
    codes = encoding(x.cfg)
    selected = defaultdict(list)
    for group in x.groups:
        for p in range(min(x.N, x.P)):
            for r in (0, 1):
                if value(x.pair.member[group.identifier,p,r]) > .5:
                    start = value(x.jobs[f'prod_{p}_{r}']['first']['s'])
                    selected[group.pjob].append((start,p,r,group))
    decoded, group_at = {}, {}
    for task, rows in selected.items():
        labels = sorted((w for w in codes if codes[w]['pjob']==task),
                        key=lambda w: codes[w]['pjob_index'])
        rows.sort(key=lambda row: row[:3])
        if len(rows) != len(labels):
            raise RuntimeError('Pjob inventory violated in exported solution')
        for row, label in zip(rows, labels):
            _, p, r, group = row
            if group.load_port != codes[label]['load_port']:
                raise RuntimeError('Pjob global release order violated in exported solution')
            decoded[p,r] = label
            group_at[p,r] = group
    return decoded, group_at


def restrict_pick_sync(x, a, b, sync):
    """Retain cross-Pjob synchronized pickup, exclude it within one Pjob."""
    if a['kind'] != 'origin_pick' or b['kind'] != 'origin_pick':
        return
    first = x.jobs[a['job']]['product']
    second = x.jobs[b['job']]['product']
    if first is None or second is None:
        return
    bytask = defaultdict(list)
    for group in x.groups:
        bytask[group.pjob].append(group)
    for groups in bytask.values():
        selected = sum(x.pair.member[g.identifier, *first] +
                       x.pair.member[g.identifier, *second] for g in groups)
        x.model.addCons(sync + selected <= 2)


def order_report(data, tolerance=1e-5):
    """Check actual product IDs, LP origins and complete initial-pick intervals."""
    from types import SimpleNamespace
    cfg = SimpleNamespace(**data['config'])
    if not hasattr(cfg, 'pjobs'):
        cfg.pjobs = None
    codes = encoding(cfg)
    picks = {e['job']: e for e in data.get('events', []) if e['kind'] == 'origin_pick'}
    tasks = defaultdict(list)
    errors = []
    seen = set()
    for job in data.get('jobs', []):
        if not job['product']:
            continue
        label = job['identity']
        if label not in codes or label in seen:
            errors.append('Unknown or repeated product: ' + label)
            continue
        seen.add(label)
        code = codes[label]
        event = picks.get(job['name'])
        if event is None:
            errors.append('Missing LP pickup: ' + label)
            continue
        if event['location'] != f"LP{code['load_port']}":
            errors.append('Encoded LP differs from pickup: ' + label)
        for field in ('pjob', 'pjob_index', 'encoded_product', 'wafer_number'):
            if field in job and job[field] != code[field]:
                errors.append('Incorrect ' + field + ': ' + label)
        tasks[code['pjob']].append((code['pjob_index'], label, event['start'], event['end']))
    if seen != set(codes):
        errors.append('Pjob product coverage differs from input')
    comparisons = 0
    for task, rows in tasks.items():
        rows.sort()
        for left, right in zip(rows, rows[1:]):
            comparisons += 1
            if right[2] <= left[2] or right[2] < left[3] - tolerance:
                errors.append(f'{task}[{left[0]}] -> {task}[{right[0]}]: '
                              f'pickup {left[2]:.9g}--{left[3]:.9g} -> {right[2]:.9g}')
    return dict(valid=not errors, errors=errors, checks=comparisons + len(seen),
                products=len(seen), pjobs=len(tasks),
                release_rule='global_pjob_index_strict_lp_pickup')
