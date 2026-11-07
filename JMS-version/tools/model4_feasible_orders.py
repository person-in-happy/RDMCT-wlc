"""Pjob schedules: enumerate physical LP/chamber choices, never product permutations.

This constructs a certified serial subset, not an MILP optimum or full-space count.
Existing model2 campaigns, exporters, and witnesses remain read-only.
"""
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import asdict
from functools import lru_cache
from datetime import datetime, timezone
import argparse, copy, gzip, hashlib, json, math, shutil, sys, time

from export_feasible_action_orders import ROOT, Config, construct, template, audit_projection, encoded, sha
from validate import validate

PERIOD = 900
CASE_H = (3, 10)


def task(lp):
    return 1 if lp == 1 else 2 if lp == 2 else 3


def allowed(lp):
    return (2,) if lp == 1 else (3,) if lp == 2 else (2, 3)


def pjobs(n, recipe):
    k = n // 4
    return [dict(id='Pjob1', mode=recipe, chambers=[2], inventory={'LP1': k}),
            dict(id='Pjob2', mode=recipe, chambers=[3], inventory={'LP2': k}),
            dict(id='Pjob3', mode=recipe, chambers=[2, 3], inventory={'LP3': k, 'LP4': k})]


@lru_cache(None)
def multiset_count(counts):
    return math.factorial(sum(counts)) // math.prod(math.factorial(v) for v in counts)


def family_count(n):
    return multiset_count((n // 4,) * 4) * 2 ** (n // 2)


def unrank_plan(n, rank):
    if n % 4 or not 0 <= rank < family_count(n):
        raise ValueError('Invalid size or rank')
    word_rank, mask = divmod(rank, 2 ** (n // 2))
    remaining = [n // 4] * 4
    plan = []
    for _ in range(n):
        for index in range(4):
            if not remaining[index]:
                continue
            remaining[index] -= 1
            block = multiset_count(tuple(remaining))
            if word_rank < block:
                lp = index + 1
                if lp < 3:
                    chamber = lp + 1
                else:
                    chamber = 2 + (mask & 1)
                    mask >>= 1
                plan.append((lp, chamber))
                break
            word_rank -= block
            remaining[index] += 1
        else:
            raise AssertionError('Unranking failed')
    assert not mask and not word_rank
    check_plan(n, plan)
    return plan


def check_plan(n, plan):
    if len(plan) != n or Counter(lp for lp, c in plan) != Counter({lp: n // 4 for lp in range(1, 5)}):
        raise ValueError('Pjob/LP inventory mismatch')
    if any(c not in allowed(lp) for lp, c in plan):
        raise ValueError('Pjob chamber eligibility')


def make_config(n, recipe, h):
    return Config(load_ports={f'LP{lp}': {'4x1': n // 4 if recipe == '4x1' else 0,
                                        '2x2': n // 4 if recipe == '2x2' else 0}
                              for lp in range(1, 5)}, cleaning_interval=h, chambers=(2, 3))


def make_blocks():
    blocks = {}
    for recipe in ('4x1', '2x2'):
        cfg = Config(load_ports={f'LP{lp}': {'4x1': int(lp == 1 and recipe == '4x1'),
                                            '2x2': int(lp == 1 and recipe == '2x2')}
                                 for lp in range(1, 5)}, cleaning_interval=3, chambers=(2, 3))
        data = construct(cfg, template(['LP1_W1'], recipe, 3, 2, 'early'))
        audit_projection(data)
        end = max([e['end'] for e in data['events']] + [c['end'] for c in data['cycles']])
        guard = max(cfg.upper_reset, cfg.lower_reset) + max(cfg.atr_empty_ll_to_lp, cfg.atr_travel, cfg.vtr_travel)
        if end + guard > PERIOD:
            raise ValueError('Composition guard exceeds period')
        if data['cycles'][-1]['mode'] != 'clean' or data['cycles'][-1]['counter'] != 0:
            raise ValueError('Block must end with completed cleaning')
        blocks[recipe] = data
    return blocks


def compose(block, plan, h):
    n = len(plan)
    recipe = next(p['mode'] for p in block['pairs'] if p['mode'] != 'clean')
    cfg = asdict(make_config(n, recipe, h))
    out = dict(schema=1, config=cfg, solutions=1, status='constructed_pjob',
               model_scope='model4_pjob_serial_family_v1', cleaning_policy='optional_before_threshold',
               pjobs=pjobs(n, recipe), events=[], jobs=[], pairs=[], cycles=[])
    product_counts = Counter()
    cycle_counts = Counter()
    for step, (lp, chamber) in enumerate(plan):
        product_counts[lp] += 1
        identity = f'LP{lp}_W{product_counts[lp]}'
        pair_offset = len(out['pairs'])
        cycle_offset = cycle_counts[chamber]
        offset = PERIOD * step
        names = {}
        for job in block['jobs']:
            j = copy.deepcopy(job)
            j['pair'] += pair_offset
            if j['product']:
                j.update(name=identity, identity=identity, origin=f'LP{lp}', pjob=f'Pjob{task(lp)}')
            else:
                member = int(j['name'].rsplit('_', 1)[1])
                j['name'] = f'aux_{j["pair"]}_{member}'
            names[job['name']] = j['name']
            for key in ('loan_start', 'loan_end', 'load_start', 'load_end', 'unload_start', 'unload_end'):
                j[key] += offset
            out['jobs'].append(j)
        for pair in block['pairs']:
            p = copy.deepcopy(pair)
            p['id'] += pair_offset
            p['chamber'] = chamber
            p['members'] = [identity if w == 'LP1_W1' else w for w in p['members']]
            out['pairs'].append(p)
        for event in block['events']:
            e = copy.deepcopy(event)
            e['start'] += offset
            e['end'] += offset
            if e['location'].startswith('LP'):
                e['location'] = f'LP{lp}'
            elif e['location'].startswith('CH'):
                e['location'] = f'CH{chamber}'
            if 'job' in e:
                e['job'] = names[e['job']]
                e['name'] = e['job'] + '_' + e['kind']
            if 'pair' in e:
                e['pair'] += pair_offset
                e['name'] = ('load_' if e['kind'] == 'pair_load' else 'unload_') + str(e['pair'])
            if 'chamber' in e:
                e['chamber'] = chamber
                e['cycle'] += cycle_offset
                side = 'after' if 'after' in e['name'] else 'before'
                e['name'] = f'rot_{side}_{chamber}_{e["cycle"]}'
            out['events'].append(e)
        for cycle in block['cycles']:
            c = copy.deepcopy(cycle)
            c.update(chamber=chamber, index=c['index'] + cycle_offset,
                     start=c['start'] + offset, end=c['end'] + offset,
                     pairs=[p + pair_offset for p in c['pairs']], front=c['front'] + pair_offset)
            out['cycles'].append(c)
        cycle_counts[chamber] += len(block['cycles'])
    out['cmax'] = max(j['loan_end'] for j in out['jobs'] if j['product'])
    return out


def check_pjobs(data, canonical=True):
    jobs = {j['name']: j for j in data['jobs']}
    pairs = {p['id']: p for p in data['pairs']}
    expected = {(p['id'], lp): number for p in data['pjobs'] for lp, number in p['inventory'].items()}
    specifications = {p['id']: p for p in data['pjobs']}
    actual = Counter()
    counts = Counter()
    for e in sorted(data['events'], key=lambda e: (e['start'], e['name'])):
        if e['kind'] != 'origin_pick' or not jobs[e['job']]['product']:
            continue
        j = jobs[e['job']]
        specification = specifications[j['pjob']]
        p = pairs[j['pair']]
        if p['chamber'] not in specification['chambers'] or p['mode'] != specification['mode']:
            raise ValueError('Pjob recipe/chamber violation')
        key = (j['pjob'], j['origin'])
        actual[key] += 1
        counts[j['origin']] += 1
        if canonical and j['identity'] != f'{j["origin"]}_W{counts[j["origin"]]}':
            raise ValueError('Noncanonical identity assignment')
    if actual != Counter(expected):
        raise ValueError('Pjob inventory coverage')
    return dict(valid=True, pjob_count=len(specifications), canonical_identities=canonical)


def audit(data):
    physics = audit_projection(data)
    return dict(physical=physics, pjob=check_pjobs(data), full_milp_solver_certification=False)


def handling(data, anonymous=False):
    jobs = {j['name']: j for j in data['jobs']}
    pairs = {p['id']: p for p in data['pairs']}
    labels = {}
    counts = Counter()
    for e in sorted(data['events'], key=lambda e: (e['start'], e['name'])):
        if e['kind'] == 'origin_pick' and jobs[e['job']]['product']:
            j = jobs[e['job']]
            key = (j.get('pjob', f'Pjob{task(int(j["origin"][2:]))}'), j['origin'])
            counts[key] += 1
            labels[j['identity']] = f'{key[0]}@{key[1]}#{counts[key]}' if anonymous else j['identity'].replace('_W', '.')
    def label(w):
        return labels[w] if w in labels else 'PEC' + w[1:]
    groups = defaultdict(list)
    locations = {'U': 'LL上层', 'L': 'LL下层', 'VS': 'PECstorage', 'AS': 'AS'}
    for e in data['events']:
        if e['robot'] not in ('ATR', 'VTR'):
            continue
        if 'pair' in e:
            members = '+'.join(label(w) for w in pairs[e['pair']]['members'])
            verb = '放' if e['kind'] == 'pair_load' else '取'
        else:
            members = label(jobs[e['job']]['identity'])
            verb = '取' if e['kind'] in ('origin_pick', 'al_pick', 'source_pick', 'lower_pick') else '放'
        groups[e['start']].append(f'{members} {e["robot"]}{verb} {locations.get(e["location"], e["location"])}')
    result = []
    for _, group in sorted(groups.items()):
        group.sort()
        result.append(group[0] if len(group) == 1 else '{ ' + ' || '.join(group) + ' }')
    return ' -> '.join(result)


def render_fragments(block):
    fragments = {}
    for lp in range(1, 5):
        for chamber in allowed(lp):
            # compose deliberately does not require equal LP inventories here.
            data = compose(block, [(lp, chamber)], 3)
            line = handling(data).replace(f'LP{lp}.1', '{product}')
            fragments[lp, chamber] = line
    return fragments


def render_plan(plan, fragments):
    counts = Counter()
    result = []
    for lp, chamber in plan:
        counts[lp] += 1
        result.append(fragments[lp, chamber].replace('{product}', f'LP{lp}.{counts[lp]}'))
    return ' -> '.join(result)


def certify_blocks(blocks):
    records = []
    for recipe, block in blocks.items():
        for lp in range(1, 5):
            for chamber in allowed(lp):
                for h in CASE_H:
                    data = compose(block, [(lp, chamber)], h)
                    data['config']['load_ports'] = {f'LP{i}': {'4x1': int(i == lp and recipe == '4x1'),
                                                              '2x2': int(i == lp and recipe == '2x2')} for i in range(1, 5)}
                    data['pjobs'] = [dict(id=f'Pjob{task(lp)}', mode=recipe, chambers=list(allowed(lp)), inventory={f'LP{lp}': 1})]
                    result = audit(data)
                    records.append(dict(recipe=recipe, lp=lp, chamber=chamber, h=h, audit=result))
    return records


def extract(base, n, number, output):
    manifest = json.loads((base / 'manifest.json').read_text('utf-8'))
    entry = next(v for v in manifest['files'] if v['n'] == n)
    for relative, expected in manifest['dependencies'].items():
        if sha(ROOT / relative) != expected:
            raise ValueError('Source dependency changed; use frozen source: ' + relative)
    if sha(base / entry['index']) != entry['index_sha256'] or sha(base/'evidence/blocks.json.gz') != manifest['blocks_sha256']:
        raise ValueError('Evidence hash mismatch')
    if not 1 <= number <= entry['count']:
        raise ValueError('Record outside exported range')
    with gzip.open(base / entry['index'], 'rt', encoding='utf-8') as stream:
        record = next(json.loads(line) for line in stream if json.loads(line)['id'] == number)
    with gzip.open(base / 'evidence/blocks.json.gz', 'rt', encoding='utf-8') as stream:
        blocks = json.load(stream)
    plan = unrank_plan(n, int(record['rank']))
    witnesses = {}
    text = None
    for h in CASE_H:
        data = compose(blocks[record['recipe']], plan, h)
        data['model4_audit'] = audit(data)
        line = handling(data)
        if hashlib.sha256(line.encode()).hexdigest() != record['sequence_sha256']:
            raise ValueError('Reconstructed sequence hash mismatch')
        witnesses[f'{record["recipe"]}_H{h}'] = data
        text = line
    output.mkdir(parents=True, exist_ok=False)
    (output / 'sequence.txt').write_text(text + '\n', 'utf-8-sig')
    (output / 'witnesses.json').write_text(json.dumps(witnesses, ensure_ascii=False, indent=2), 'utf-8')
    print('EXTRACTED AND REVALIDATED ' + str(output), flush=True)


def run(a):
    base = Path(a.output).resolve()
    if not base.is_relative_to(ROOT / 'JMS-version/gif/kexingyu'):
        raise ValueError('Output must be inside gif/kexingyu')
    base.mkdir(parents=True, exist_ok=False)
    evidence = base / 'evidence'
    evidence.mkdir()
    started = time.monotonic()
    dependencies = [Path(__file__), ROOT/'JMS-version/tools/export_feasible_action_orders.py',
                    ROOT/'JMS-version/tools/feasible_order_titles.py', ROOT/'JMS-version/joint_model/seed.py',
                    ROOT/'JMS-version/joint_model/model.py', ROOT/'JMS-version/joint_model/validate.py',
                    ROOT/'JMS-version/joint_model/grippers.py', ROOT/'joint_pairing_model.py', ROOT/'joint_chamber_cycle_model.py']
    frozen = evidence / 'frozen_code'
    for source in dependencies:
        target = frozen / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    blocks = make_blocks()
    certification = certify_blocks(blocks)
    with gzip.open(evidence/'blocks.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(blocks, stream, ensure_ascii=False, separators=(',', ':'))
    manifest = dict(created_utc=datetime.now(timezone.utc).isoformat(), model='model4_pjob',
        complete_enumeration=False, all_feasible_orders=None,
        construction_family='Serial one-product blocks; completed cleaning after every product; canonical per-Pjob/LP identities.',
        lower_bound_formula='n! / ((n/4)!)^4 * 2^(n/2)', block_period_seconds=PERIOD,
        counting='Handling-only start-order groups; numeric times excluded; anonymous Pjob/LP occurrence identity canonicalized; H=3 and H=10 merged.',
        resources=dict(concurrency=1, solver_processes=0, gpu_jobs=0, execution='visible foreground'),
        validation_scope='Every output: inventory, eligibility, canonical decoding, distinct sequence hash. Every block: full physical replay. First/middle/last rank of every size/recipe/H: full replay. No per-output MILP solve.',
        composition_proof='Every block returns all material and ends after cleaning at count zero. The 900-second spacing exceeds block end plus LL reset and maximum robot movement. All cross-block robot pairs, gripper/module/identity loans and chamber resets are therefore feasible. Remapping the sole product LP and the sole chamber preserves within-block durations; all permitted mappings are replayed.',
        dependencies={str(p.relative_to(ROOT)): sha(p) for p in dependencies},
        blocks_sha256=sha(evidence/'blocks.json.gz'), block_audits=certification, files=[])
    fragments = {recipe: render_fragments(block) for recipe, block in blocks.items()}
    for n, quota in zip(a.sizes, a.counts):
        total = family_count(n)
        if quota > 2*total or quota < 2:
            raise ValueError('Invalid export quota')
        print(f'n={n} preparing full witness audits completed=0/12 failed=0 ETA=pending', flush=True)
        audit_path = evidence / f'{n}wafer-representatives.jsonl.gz'
        checks = 0
        with gzip.open(audit_path, 'wt', encoding='utf-8') as stream:
            for recipe in blocks:
                for h in CASE_H:
                    for rank in (0, total//2, total-1):
                        data = compose(blocks[recipe], unrank_plan(n, rank), h)
                        result = audit(data)
                        assert handling(data) == render_plan(unrank_plan(n, rank), fragments[recipe])
                        stream.write(encoded(dict(recipe=recipe, h=h, rank=str(rank), audit=result, witness=data))+'\n')
                        checks += 1
                        print(f'n={n} full_replays completed={checks}/12 failed=0 elapsed={time.monotonic()-started:.1f}s', flush=True)
        path = base / f'模型4_{n}wafer_已列{quota}种_每配置至少{total}种_简化取放.txt'
        index_path = evidence / f'{n}wafer-index.jsonl.gz'
        unique = set()
        recipe_counts = Counter()
        began = time.monotonic()
        with path.open('wb') as stream, gzip.open(index_path, 'wt', encoding='utf-8') as index:
            stream.write((f'模型4：{n}片；已列{quota}种；每个固定配置至少{total}种。\n'
                '只列晶圆、ATR/VTR取放动作和位置，按开始时间排序；同刻动作以{... || ...}表示。\n'
                'Pjob1仅CH2，来自LP1；Pjob2仅CH3，来自LP2；Pjob3允许CH2/CH3，来自LP3、LP4；四LP等量。\n'
                '每条覆盖全部产品与实际辅助片取放；隐藏时间、旋转和曝光仍在可重建证据中。\n'
                '仅同Pjob同LP身份置换不另计数；来源次序与合法腔室分配不同才形成本构造族的新方案。\n'
                '四配置：纯4x1/2x2 × H=3/10；同一取放顺序适用两个H时合并。每产品后完整清洁，非最优性结论。\n'
                '完整空间总数未知；本文件为确定性抽取子集。公式给出构造族精确大小，也是整个模型的数量下界。\n\n').encode('utf-8-sig'))
            for i in range(quota):
                recipe = ('4x1', '2x2')[i % 2]
                local = i // 2
                local_total = (quota + (1 if i % 2 == 0 else 0)) // 2
                rank = 0 if local_total == 1 else local * (total-1) // (local_total-1)
                plan = unrank_plan(n, rank)
                line = render_plan(plan, fragments[recipe])
                digest = hashlib.sha256(line.encode('utf-8')).hexdigest()
                if digest in unique:
                    raise ValueError('Duplicate canonical sequence')
                unique.add(digest)
                recipe_counts[recipe] += 1
                offset = stream.tell()
                raw = (f'[{i+1:06d}] 配置={recipe}_H3,{recipe}_H10 | 构造编号={rank}\n{line}\n\n').encode('utf-8')
                stream.write(raw)
                index.write(encoded(dict(id=i+1, recipe=recipe, rank=str(rank), offset=offset,
                                         bytes=len(raw), sequence_sha256=digest))+'\n')
                if (i+1) % 1000 == 0 or i+1 == quota:
                    elapsed = time.monotonic()-began
                    print(f'n={n} completed={i+1}/{quota} failed=0 elapsed={elapsed:.1f}s ETA={elapsed/(i+1)*(quota-i-1):.1f}s', flush=True)
        with path.open('rb') as source, gzip.open(str(path)+'.gz', 'wb', compresslevel=6) as target:
            shutil.copyfileobj(source, target)
        row = dict(n=n, path=path.name, compressed_path=path.name+'.gz', count=len(unique),
            per_configuration={f'{recipe}_H{h}': recipe_counts[recipe] for recipe in blocks for h in CASE_H},
            family_count_per_configuration=str(total), full_space_count=None, complete_enumeration=False,
            sha256=sha(path), compressed_sha256=sha(str(path)+'.gz'), bytes=path.stat().st_size,
            index=str(index_path.relative_to(base)), index_sha256=sha(index_path),
            representative_witnesses=str(audit_path.relative_to(base)), representative_sha256=sha(audit_path),
            full_replays=checks, maximum_complete_time=PERIOD*(n-1)+max(e['end'] for e in blocks['2x2']['events']))
        manifest['files'].append(row)
        (base/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    manifest['elapsed_seconds'] = time.monotonic()-started
    manifest['status'] = 'completed'
    manifest['failed'] = 0
    (base/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    print(f'COMPLETE completed={sum(a.counts)} failed=0 elapsed={manifest["elapsed_seconds"]:.1f}s', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', default='JMS-version/gif/kexingyu/model4_pjob_20261027')
    parser.add_argument('--sizes', nargs='+', type=int, default=[8, 16, 32])
    parser.add_argument('--counts', nargs='+', type=int, default=[40320, 50000, 60000])
    parser.add_argument('--extract', nargs=2, type=int, metavar=('N', 'ID'))
    parser.add_argument('--extract-output')
    args = parser.parse_args()
    if args.extract:
        extract(Path(args.output).resolve(), *args.extract, Path(args.extract_output).resolve())
    else:
        if len(args.sizes) != len(args.counts):
            parser.error('sizes and counts lengths differ')
        run(args)
