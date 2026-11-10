import sys,json,math
from pathlib import Path
from collections import defaultdict,Counter
from statistics import mean
sys.path.insert(0,'JMS-version/tools')
import default_gap_experiments as g
revision=g.JMS/'revisions/20261108_encoding_update'
reports=[]
for name in ('gap_d_encoding_20261108_r2','gap_d_structure_20261108_r1'):
    out=g.RESULTS/name;spec=g.checked(out);rows=[];groups=defaultdict(list)
    for c in spec['cells']:
        folder=out/'runs'/c['id']
        if not (folder/'evidence.json').exists():continue
        ev=g.read(folder/'evidence.json');r=g.read(folder/'result.json');res=g.read(folder/'resources.json')
        assert res['exit_code']==0 and not (folder/'failure.json').exists()
        assert g.digest(folder/'result.json')==ev['result_sha256']
        if 'variables_sha256' in ev:assert g.digest(folder/'variables.json')==ev['variables_sha256']
        assert ev['cell']==c and ev['valid'] and r['original_model_check']
        assert r['config']==g.read(c['config'])
        replay=g.validate(r);assert replay['valid']
        met=g.review.physical_metrics(r)
        for k,v in met.items():
            if isinstance(v,(int,float)):assert math.isclose(v,ev['metrics'][k],abs_tol=2e-4,rel_tol=0),(c['id'],k)
        row=dict(id=c['id'],case=c['case'],seed=c['seed'],arm=c['arm'],state=ev['state'],metrics=met,
            result_sha256=ev['result_sha256'],evidence_sha256=g.digest(folder/'evidence.json'),
            resources_sha256=g.digest(folder/'resources.json'),replay=replay)
        if spec['suite']=='encoding':
            assert ev['full_model_audit']['valid'] and ev['full_model_audit']['original_model_check']
            assert r['full_candidate_space']
            assert ev['common_warm_sha256']==g.digest(Path(c['values']))
            assert abs(ev['lower_bound']-r['dual_bound'])<2e-4
            row.update(lower=ev['lower_bound'],upper=met['product_cmax'],seconds=ev['solve_seconds'],
                dimensions=ev['dimensions'],warm_sha256=ev['common_warm_sha256'],source_cmax=ev['source_metrics']['product_cmax'])
            groups[c['case'],c['arm']].append(row)
        rows.append(row)
    summary=[]
    for (case,arm),rr in groups.items():
        assert sorted(r['seed'] for r in rr)==[1,2,3]
        assert len({json.dumps(r['dimensions'],sort_keys=True) for r in rr})==1
        summary.append(dict(case=case,arm=arm,states=dict(Counter(r['state'] for r in rr)),
            mean_lower=mean(r['lower'] for r in rr),mean_upper=mean(r['upper'] for r in rr),
            lower_range=[min(r['lower'] for r in rr),max(r['lower'] for r in rr)],
            upper_range=[min(r['upper'] for r in rr),max(r['upper'] for r in rr)],
            mean_solve_seconds=mean(r['seconds'] for r in rr),dimensions=rr[0]['dimensions']))
    if spec['suite']=='encoding':
        for case in set(r['case'] for r in rows):
            assert len({r['warm_sha256'] for r in rows if r['case']==case})==1
    reports.append(dict(campaign=name,campaign_sha256=g.digest(out/'campaign.json'),settings=spec['settings'],
        expected=len(spec['cells']),observed=len(rows),states=dict(Counter(r['state'] for r in rows)),rows=rows,summary=summary,
        scope='Frozen inputs/code/result hashes checked; saved original and lifted-model certificates checked; fresh physical replay and metric recomputation; no solver'))
g.dump(revision/'evidence.json',reports)
for r in reports:
    print(r['campaign'],r['expected'],r['observed'],r['states'])
    for s in r['summary']:print(json.dumps(s))
