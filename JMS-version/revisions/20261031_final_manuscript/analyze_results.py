"""Compute manuscript statistics from independently verified records."""
from pathlib import Path
from collections import defaultdict, Counter
from statistics import mean
import json
import math

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / 'verified_results.json').read_text('utf-8'))
ROWS = DATA['rows']


def grouped(rows, key):
    out = defaultdict(list)
    for row in rows:
        out[key(row)].append(row)
    return out


def stats():
    results = {}
    refine = [r for r in ROWS if r['suite'] in ('paper', 'qualification') and r['variant'] == 'refined']
    table = []
    for (suite, case), g in grouped(refine, lambda r: (r['suite'], r['case'])).items():
        b = mean(r['phase1_metrics']['route_wait_sum'] for r in g)
        a = mean(r['metrics']['route_wait_sum'] for r in g)
        table.append(dict(suite=suite, case=case, n=g[0]['product_count'], h=g[0]['h'], source=g[0]['source'],
                          c1=mean(r['phase1_cmax'] for r in g), c2=mean(r['upper'] for r in g),
                          wait1=b, wait2=a, percent=100*(b-a)/b,
                          run_percent=[100*(r['phase1_metrics']['route_wait_sum']-r['metrics']['route_wait_sum'])/r['phase1_metrics']['route_wait_sum'] for r in g],
                          max_wait=max(r['metrics']['route_wait_max'] for r in g),
                          max_cmax_increase=max(r['upper']-r['phase1_cmax'] for r in g)))
    results['refinement'] = table
    init = []
    for case in ('n4_H3_mixed_dual','n4_H3_mixed_single','n4_H10_mixed_dual','n8_H3_mixed_dual'):
        arms = {arm: [r for r in ROWS if r['suite']=='paper' and r['case']==case and r['variant']==arm]
                for arm in ('cold','serial','joint')}
        c_serial, c_spbs = (mean(r['upper'] for r in arms[arm]) for arm in ('serial','joint'))
        init.append(dict(case=case, counts={a:sum(r['has_solution'] for r in g) for a,g in arms.items()},
                         serial=c_serial,spbs=c_spbs,percent=100*(c_serial-c_spbs)/c_serial,
                         spbs_offline_seconds=arms['joint'][0]['offline_seconds']))
    results['initialization'] = init
    rhythm=[]
    for (source,arm),g in grouped([r for r in ROWS if r['suite']=='rhythm' and r['variant']!='joint'],lambda r:(r['source'],r['variant'])).items():
        rhythm.append(dict(source=source,arm=arm,count=len(g),cmax=mean(r['upper'] for r in g),
                           wait1=mean(r['phase1_metrics']['route_wait_sum'] for r in g),wait2=mean(r['metrics']['route_wait_sum'] for r in g),
                           rhythm1=mean(r['phase1_metrics']['rhythm_deviation'] for r in g),rhythm2=mean(r['metrics']['rhythm_deviation'] for r in g),
                           centers=sorted(set(r['metrics']['rhythm_centers'] for r in g)),maxwait=max(r['metrics']['route_wait_max'] for r in g),
                           seconds=mean(r['secondary_solve_seconds'] for r in g)))
    results['rhythm']=rhythm
    paired=[]
    for key,g in grouped([r for r in ROWS if r['suite']=='rhythm' and r['variant']!='joint'],lambda r:(r['case'],r['seed'])).items():
        assert len(g)==3
        assert len(set(r['warm_sha256'] for r in g))==1
        assert max(r['phase1_cmax'] for r in g)-min(r['phase1_cmax'] for r in g)<1e-5
        assert all(r['phase1_metrics']==g[0]['phase1_metrics'] for r in g)
        assignments = [json.loads((HERE.parents[2] / 'JMS-version/results' / r['campaign'] / 'runs' / r['id'] / 'variables_phase1.json').read_text('utf-8'))['values'] for r in g]
        assert all(a.keys() == assignments[0].keys() for a in assignments)
        difference = max(abs(value-a[name]) for a in assignments[1:] for name,value in assignments[0].items())
        assert difference <= 1e-6, (key,difference)
        paired.append(dict(case=key[0],seed=key[1],same_primary_assignment_within_tolerance=True,
                           maximum_value_difference=difference,
                           note='Compare values, not the assignment file hash, which includes a run-specific compressed LP hash'))
    results['rhythm_pairing']=paired
    cuts = [r for r in ROWS if r['suite']=='paper_cuts']
    cutstats=[]
    for arm,g in grouped(cuts,lambda r:r['variant']).items():
        by_case=grouped(g,lambda r:r['case'])
        cutstats.append(dict(arm=arm,feasible=sum(r['has_solution'] for r in g),cmax_case_mean=mean(mean(r['upper'] for r in v) for v in by_case.values()),
                             callback_runs=sum((r['cut_telemetry'] or {}).get('callback_calls',0)>0 for r in g),
                             callback_seconds_mean=mean((r['cut_telemetry'] or {}).get('callback_time_seconds',0) for r in g)))
    results['cuts']=cutstats
    identical=0
    for key,g in grouped(cuts,lambda r:(r['case'],r['seed'])).items():
        d={r['variant']:r for r in g}
        assert len(set(r['warm_sha256'] for r in g))==1
        identical+=abs(d['proposed']['upper']-d['joint']['upper'])<1e-4
    results['proposed_scip_identical_cmax_pairs']=identical
    scale=[]
    for case,g in grouped([r for r in ROWS if r['suite']=='scale32'],lambda r:r['case']).items():
        scale.append(dict(case=case,cmax=mean(r['upper'] for r in g),status=sorted(set(r['status'] for r in g)),
                          variables=g[0]['build']['dimensions']['variables'],constraints=g[0]['build']['dimensions']['constraints'],
                          x_variables=g[0]['build']['dimensions']['pjob_inventory_variables'],
                          peak_gib=max(r['resources']['peak_sampled_rss_mib']/1024 for r in g),
                          primary_seconds=[r['primary_solve_seconds'] for r in g]))
    results['scale32']=scale
    results['time_ranges']={s:[min(r['primary_solve_seconds'] for r in g),max(r['primary_solve_seconds'] for r in g)]
                           for s,g in grouped(ROWS,lambda r:r['suite']).items()}
    results['revalidated_totals']={k:DATA[k] for k in ('completed','feasible','original_attempt_failures','primary_states')}
    results['constructive_counts']={n:math.factorial(n)//(math.factorial(n//4)**2*math.factorial(n//2))*2**(n//2) for n in (8,16,32)}
    (HERE/'statistics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    stats()
