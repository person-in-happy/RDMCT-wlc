from pathlib import Path
from collections import defaultdict, Counter
from statistics import mean
import hashlib
import importlib.util
import json
import math
import re
import sys

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
ROOT = PAPER.parent
sys.path.insert(0, str(PAPER / 'experiments/nondecreasing_followup_20261102'))
import followup_models as f


def read(p):
    return json.loads(p.read_text('utf-8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


oldmetrics_spec = importlib.util.spec_from_file_location('independent_metrics', PAPER / 'revisions/20261101_deep_review/audit_review.py')
oldmetrics = importlib.util.module_from_spec(oldmetrics_spec)
oldmetrics_spec.loader.exec_module(oldmetrics)
audit = read(HERE / 'newrule_validation.json')
rows = audit['rows']
assert not audit['failures'] and audit['assignments_checked'] == 180
byfile = {str(ROOT / r['directory'] / r['result']):r for r in rows}
phase_pairs, cleanup, groups = [], [], defaultdict(list)
for r in rows:
    if r['category'] in ('basic','qualification','rhythm') and r['result'] == 'result.json':
        groups[r['category'],r['cell']['case'],r['cell']['variant']].append(r)
    if r['category'] in ('basic','qualification') and r['result'] == 'result.json':
        p=ROOT/r['directory'];before=byfile[str(p/'phase1.json')]
        assert r['metrics']['product_cmax'] <= before['metrics']['product_cmax'] + 2e-4
        a,b=oldmetrics.metrics(read(p/'phase1.json')),oldmetrics.metrics(read(p/'result.json'))
        assert abs((b['product_flow_sum']-a['product_flow_sum'])-(b['product_route_wait']-a['product_route_wait'])-(b['product_chamber_sum']-a['product_chamber_sum']))<2e-3
        phase_pairs.append(dict(case=r['cell']['case'],seed=r['cell']['seed'],before=a,after=b,
            total_before=before['metrics']['route_wait_sum'],total_after=r['metrics']['route_wait_sum']))
    if r['category']=='cleanup':
        source=byfile[str(Path(r['cell']['source']))]
        a,b=source['metrics'],r['metrics']
        objective=lambda ms: ms['route_wait_sum']+10*ms['route_wait_max']+25*ms['rhythm_deviation']
        assert b['product_cmax'] <= a['product_cmax']+2e-4
        assert objective(b) <= objective(a)+2e-3
        assert b['modeled_completion'] <= a['modeled_completion']+2e-4
        cleanup.append(dict(case=r['cell']['case'],id=r['cell']['id'],before=a['modeled_completion'],after=b['modeled_completion'],cmax=b['product_cmax']))

def skeleton(d):
    return ([{k:p[k] for k in ('id','members','mode','chamber')} for p in d['pairs']],
            [{k:c[k] for k in ('chamber','index','mode','pairs','front')} for c in d['cycles']])

ablation=[]
rhythm=PAPER/'results/pjob_fifo_rhythm_all_20261030_124059/runs'
for case in dict.fromkeys(r['cell']['case'] for r in rows if r['category']=='rhythm'):
    for seed in (1,2,3):
        sources=[rhythm/f'{case}__s{seed}__{arm}' for arm in ('refined','waiting_only','quadratic')]
        starts=[read(p/'phase1.json') for p in sources]
        same=skeleton(starts[0])==skeleton(starts[1])==skeleton(starts[2])
        assert same, (case,seed)
        ablation.append(dict(case=case,seed=seed,same_initial_structure=True,
            results={arm:byfile[str(p/'result.json')]['metrics'] for arm,p in zip(('refined','waiting_only','quadratic'),sources)}))

enum=PAPER/'gif/kexingyu/pjob_fifo_20261029'
manifest=read(enum/'manifest.json');sequences={};enum_hashes={}
for n, info in manifest['sizes'].items():
    path=enum/info['file'];assert sha(path)==info['sha256'];enum_hashes[str(path.relative_to(ROOT))]=sha(path)
    txt=path.read_text('utf-8');orders=re.findall(r'^实际晶圆：(.+)$',txt,re.M)
    assert len(orders)==info['count']
    N=int(n);a=N//4;tasks={1:[],2:[],3:[]}
    for lp in range(1,5):
        tasks[min(lp,3)].extend(25*(lp-1)+s for s in range(1,a+1))
    expected=sorted(w for products in tasks.values() for w in products)
    for line in orders:
        order=[int(v) for v in line.split(',')]
        assert sorted(order)==expected
        for products in tasks.values():assert [w for w in order if w in products]==products
    bound=math.factorial(N)//(math.factorial(a)**2*math.factorial(2*a))*2**(2*a)
    assert bound==info['lower_bound_per_configuration']
    sequences[n]=dict(count=len(orders),lower_bound=bound,per_recipe=info['per_recipe'])
examples=[]
for example in manifest['examples']:
    path=enum/example['file'];data=read(path);check=f.validate(data)
    assert check['valid'], (path,check)
    examples.append(dict(file=str(path.relative_to(ROOT)),sha256=sha(path),checks=check['checks']))
summary=[]
for (cat,case,variant), rr in groups.items():
    summary.append(dict(category=cat,case=case,variant=variant,seeds=len(rr),
        metrics={k:mean(r['metrics'][k] for r in rr) for k,v in rr[0]['metrics'].items() if isinstance(v,(int,float))}))
report=dict(phase_pairs=phase_pairs,ablation=ablation,cleanup=cleanup,
    cleanup_improved=sum(r['after']<r['before']-2e-4 for r in cleanup),
    summaries=summary,sequences=sequences,sequence_examples=examples,sequence_hashes=enum_hashes,
    optimization_calls=0)
(HERE/'derived_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps(dict(pairs=len(phase_pairs),ablation=len(ablation),cleanup=len(cleanup),cleanup_improved=report['cleanup_improved'],sequence_examples=len(examples)),indent=2))
