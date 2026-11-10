"""Read frozen evidence for review, without solving or changing any run."""
from pathlib import Path
from collections import defaultdict, Counter
from statistics import mean
import hashlib
import json

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]


def read(p):
    return json.loads(p.read_text('utf-8-sig'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def physical_metrics(data):
    cfg = data['config']
    events = defaultdict(dict)
    for e in data['events']:
        if 'job' in e:
            events[e['job']][e['kind']] = e
    waits = defaultdict(list)
    max_dwell = defaultdict(float)
    for j in data['jobs']:
        es = events[j['name']]
        group = 'product' if j['product'] else 'dummy'
        vals = [j['load_start']-es['source_pick']['end']-cfg['vtr_travel'],
                es['destination_put']['start']-j['unload_end']-cfg['vtr_travel']]
        max_dwell['robot'] = max(max_dwell['robot'], j['load_end']-es['source_pick']['start'],
                                es['destination_put']['end']-j['unload_start'])
        max_dwell['chamber'] = max(max_dwell['chamber'], j['unload_start']-j['load_end'])
        if j['origin'] != 'VS':
            if 'al_put' in es:
                legs = [('origin_pick','al_put',cfg['atr_travel']),
                        ('al_put','al_pick',cfg['alignment']),('al_pick','upper_put',cfg['atr_travel'])]
                max_dwell['al'] = max(max_dwell['al'], es['al_pick']['start']-es['al_put']['end'])
                hand_times = [es['al_put']['end']-es['origin_pick']['start'],
                              es['upper_put']['end']-es['al_pick']['start']]
            else:
                legs = [('origin_pick','upper_put',cfg['atr_travel'])]
                hand_times = [es['upper_put']['end']-es['origin_pick']['start']]
            legs += [('upper_put','source_pick',cfg['pump']),
                     ('destination_put','lower_pick',cfg['vent']),('lower_pick','origin_put',cfg['atr_travel'])]
            vals += [es[b]['start']-es[a]['end']-dt for a,b,dt in legs]
            max_dwell['robot'] = max(max_dwell['robot'], *hand_times,
                                    es['origin_put']['end']-es['lower_pick']['start'])
            max_dwell['ll'] = max(max_dwell['ll'], es['source_pick']['start']-es['upper_put']['end'],
                                 es['lower_pick']['start']-es['destination_put']['end'])
        assert min(vals) >= -2e-4
        waits[group] += [max(0, v) for v in vals]
    return {
        'wait': {g: {'sum': sum(w), 'max': max(w,default=0), 'count':len(w)} for g,w in waits.items()},
        'max_dwell': dict(max_dwell),
        'cycles': dict(Counter(c['mode'] for c in data['cycles'])),
        'production_per_chamber': {str(c):sum(x['chamber']==c and x['mode']!='clean' for x in data['cycles'])
                                    for c in cfg['chambers']},
        'product_completion': data['cmax'],
        'last_physical_event': max(e['end'] for e in data['events']),
    }


def main():
    data = read(PAPER / 'revisions/20261031_final_manuscript/verified_results.json')
    rows = data['rows']
    groups = defaultdict(list)
    physical = []
    metadata_hashes_checked = 0
    for r in rows:
        groups[r['suite'],r['variant']].append(r)
        run = PAPER / 'results' / r['campaign'] / 'runs' / r['id']
        for name in ('phase1.json','result.json','evidence.json','manifest.json'):
            assert sha(run/name) == r['hashes'][name], str(run/name)
            metadata_hashes_checked += 1
        if r['has_solution']:
            first, last = (physical_metrics(read(run/name)) for name in ('phase1.json','result.json'))
            assert abs(sum(x['sum'] for x in last['wait'].values())-r['metrics']['route_wait_sum'])<1e-3
            physical.append(dict(campaign=r['campaign'],cell=r['id'],case=r['case'],suite=r['suite'],
                                 variant=r['variant'],seed=r['seed'],phase1=first,final=last))
    summary = []
    for (suite,variant),group in groups.items():
        feasible=[r for r in group if r['has_solution']]
        warmed=[r for r in feasible if r['warm_sha256'] is not None]
        summary.append(dict(suite=suite,variant=variant,runs=len(group),feasible=len(feasible),
                            primary_improved_warm=sum(r['phase1_cmax']<r['initial_cmax']-1e-4 for r in warmed),
                            final_improved_warm=sum(r['upper']<r['initial_cmax']-1e-4 for r in warmed),
                            nodes=dict(Counter(r['nodes'] for r in group)),
                            positive_lower_bounds=sum(r['lower'] is not None and r['lower']>1e-6 for r in feasible)))
    refined_groups=defaultdict(list)
    for r in physical:
        if r['suite'] in ('paper','qualification') and r['variant']=='refined':
            refined_groups[r['suite'],r['case']].append(r)
    waits=[]
    for (suite,case),g in refined_groups.items():
        item=dict(suite=suite,case=case)
        for kind in ('product','dummy'):
            before=mean(r['phase1']['wait'][kind]['sum'] for r in g)
            after=mean(r['final']['wait'][kind]['sum'] for r in g)
            item[kind]=dict(before=before,after=after,reduction_percent=(before-after)/before*100 if before else None)
        waits.append(item)
    rhythm = [r for r in physical if r['suite']=='rhythm']
    refs=[]
    for c in data['campaigns']:
        for path in sorted((PAPER/'results'/c['name']/'references').glob('*/certificate.json')):
            cert=read(path)
            refs.append(dict(campaign=c['name'],case=path.parent.name,cmax=cert['cmax'],seconds=cert['seconds'],
                             levels=read(path.parent/'spbs_levels.json')))
    report=dict(source_sha256=sha(PAPER/'JMS_Review_CN.tex'),
                verified_input_sha256=sha(PAPER/'revisions/20261031_final_manuscript/verified_results.json'),
                metadata_hashes_checked=metadata_hashes_checked,
                unique_case_ids=len({r['case'] for r in rows}),
                grouped_search_results=summary,wait_by_product_and_dummy=waits,
                rhythm_runs=len(rhythm),
                rhythm_no_cleaning_runs=sum(r['final']['cycles'].get('clean',0)==0 for r in rhythm),
                final_max_dwell={k:max(p['final']['max_dwell'].get(k,0) for p in physical)
                                 for k in ('robot','chamber','al','ll')},
                physical_metrics=physical,reference_preparation=refs)
    example_path = PAPER/'results/pjob_fifo_paper_all_20261030_075555/runs/n4_H3_mixed_single__s1__refined/result.json'
    example = read(example_path)
    job = next(j for j in example['jobs'] if j['name']=='aux_7_1')
    cycles = [c for c in example['cycles'] if job['pair'] in c['pairs']]
    report['terminal_cleanup_example'] = dict(path=str(example_path.relative_to(PAPER)),
        sha256=sha(example_path),product_cmax=example['cmax'],job=job,cycles=cycles,
        unload_wait_after_cleaning=job['unload_start']-max(c['end'] for c in cycles),
        last_event=max(e['end'] for e in example['events']),validation=example['validation'])
    report['fixed_comparison'] = [{k:r[k] for k in ('id','variant','seed','upper','lower','initial_cmax',
                                                  'primary_solve_seconds','warm_sha256')}
        for r in rows if r['suite']=='paper' and r['case']=='n4_H10_mixed_dual'
        and r['variant'] in ('joint','fixed','partition')]
    report['refined_rhythm_centers'] = {suite: dict(Counter(r['metrics']['rhythm_centers']
        for r in rows if r['suite']==suite and r['variant']=='refined'))
        for suite in ('paper','qualification','rhythm')}
    (HERE/'audit_metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(metadata_hashes_checked=metadata_hashes_checked,completed=len(rows),
                         feasible=len(physical),rhythm_without_cleaning=report['rhythm_no_cleaning_runs'],
                         tail=report['terminal_cleanup_example']['last_event']),ensure_ascii=False))


if __name__ == '__main__':
    main()
