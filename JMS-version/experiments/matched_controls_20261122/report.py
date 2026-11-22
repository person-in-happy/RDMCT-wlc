"""Report only validated, budget-eligible, same-seed comparisons; signs are not filtered."""
import argparse
import statistics
import time

from run import ARMS, LARGE, METHODS, OUT, SMALL, read, sha


def report():
    design = read(OUT/'design.json')
    records = {}
    excluded = []
    for case, seed, arm in design['jobs']:
        folder = OUT/f'{case}__s{seed}__{arm}'
        if not (folder/'result.json').exists(): continue
        result = read(folder/'result.json')
        stages = (['free'] if arm in ARMS else ([] if arm == 'plain_full' else ['spbs']) + ['primary'])
        if arm not in ('A', 'B'): stages.append('retime')
        for name, stage in zip(stages, result['stages'], strict=True):
            if not (stage['replay']['valid'] and stage['rows'] > 0 and all(
                    sha(folder/name/file) == stage[key] for file,key in
                    [('schedule.json','schedule_sha256'), ('assignment.json.gz','assignment_sha256')])):
                raise ValueError(f'Invalid witness: {folder}/{name}')
        if result['eligible']: records[case,seed,arm] = result
        else: excluded.append(folder.name)
    lines = ['# 同预算对照：仅汇总已完成、可配对的运行', '',
             '每个差值均为同一种子下「完整方案减对照」，两列均为负值较好；两阶段不要求两个指标同时下降。4/8片比较相同SCIP模型的目标策略。16片比较完整学习策略与替代方法；省略初始化的一组将60 s还给主搜索。训练种子固定为1。', '',
             '|实例|完整方案|对照|配对种子（计划3）|平均工期差/s|平均工艺目标差|', '|---|---|---|---|---:|---:|']
    for case in SMALL + LARGE:
        full = 'AB' if case in SMALL else 'full'
        for arm in (ARMS if case in SMALL else METHODS):
            if arm == full: continue
            pairs = []
            for seed in (1,2,3):
                main, ref = (records.get((case,seed,item)) for item in (full,arm))
                if not main or not ref: continue
                if main['input_sha256'] != ref['input_sha256']: raise ValueError('Different raw inputs')
                if case in LARGE and arm != 'plain_full' and main['stages'][0]['schedule_sha256'] != ref['stages'][0]['schedule_sha256']:
                    raise ValueError('Different SPBS schedules')
                pairs.append((seed, *(main['metrics'][key]-ref['metrics'][key] for key in ('cmax','secondary'))))
            values = [f'{statistics.mean(row[col] for row in pairs):.2f}' if pairs else '—' for col in (1,2)]
            lines.append('|'+ '|'.join([case,full,arm,','.join(str(row[0]) for row in pairs) or '无',*values])+'|')
    lines.extend(['',f'已核验终值：{len(records)+len(excluded)}/{len(design["jobs"])}；超预算或资源中止单列：'+(', '.join(excluded) or '无')])
    path = OUT/'COMPARISONS_CN.md'
    temporary = path.with_suffix('.tmp'); temporary.write_text('\n'.join(lines)+'\n', encoding='utf-8'); temporary.replace(path)
    return len(records)+len(excluded)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--follow', action='store_true'); options = parser.parse_args()
    previous = -1
    while True:
        progress = read(OUT/'progress.json')
        if previous != progress['completed'] or not progress['remaining']:
            count = report(); previous = progress['completed']; print(f'Validated end points: {count}', flush=True)
        if not options.follow or not progress['remaining']: break
        time.sleep(30)
