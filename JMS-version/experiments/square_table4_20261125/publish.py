"""Recalculate and certify all three comparison arms for the global quadratic range penalty."""
import csv
import hashlib
import json
import os
import statistics
import sys
from collections import defaultdict
from itertools import product
from pathlib import Path

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
OUT=JMS/'results'/HERE.name
OLD=JMS/'results/huber_residence_20261125'
EXT=JMS/'results/table4_extended16_20261125'
CASES=((2,3),(4,3),(4,10),(8,3),(8,10),(16,3),(16,10))
SEEDS=(1,2,3)
TOL=2e-5
sys.path.insert(0,str(JMS/'model4_pjob_nonprocessing_20261103'))
from validate import validate


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temp.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf8');os.replace(temp,path)


def rel(path):
    return path.relative_to(JMS).as_posix()


def load_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def scores(doc):
    cfg=doc['config'];h=cfg['cleaning_interval'];groups=defaultdict(list);duration=defaultdict(float)
    kinds={}
    for row in doc['cycles']:
        for pair in row['pairs']:
            duration[pair]+=row['end']-row['start'];kinds[pair]=row['mode']
    e=0
    for chamber in cfg['chambers']:
        before=0
        for row in sorted((r for r in doc['cycles'] if r['chamber']==chamber),key=lambda r:r['index']):
            if row['mode']=='clean':
                assert 1<=before<=h
                e+=h-before;before=0
            else:before+=1
            assert row['counter']==before<=h
    last=0
    for wafer in doc['jobs']:
        if wafer['product']:
            j=wafer['pair']
            groups[kinds[j]].append(max(0.,wafer['unload_start']-wafer['load_end']-duration[j]))
            last=max(last,wafer['loan_end'])
    n=sum(map(len,groups.values()));m=len(groups['2x2'])
    assert n==2*m and groups['4x1']
    mean=sum(map(sum,groups.values()))/n;spread=max(max(r)-min(r) for r in groups.values())
    return dict(n=n,H=h,f_A=last,f_B=mean+spread**2/2+e,mean=mean,spread=spread,E=e,penalty=spread**2/2)


def lower_bound(n,h):
    # A nonterminal product pair can contain two wafers for each of its H-2
    # slots; the remaining products include one or two terminal wafers.
    m=n//2
    terminal=[0]+[m+1]*m
    for k in range(1,m+1):
        for pairs in range(1,min(h-1,k)+1):
            for count in range(pairs,min(2*pairs,k)+1):
                terminal[k]=min(terminal[k],terminal[k-count]+(2 if count==2*pairs else 1))
    a=(m-terminal[m])/n
    return dict(terminal=terminal[m],a=a,analytic_lower=3.5-a*a/2)


def replay(folder,cert,verify=True):
    raw=read(cert);schedule=folder/'schedule.json';assignment=folder/'assignment.json.gz'
    files=raw.get('files') or {'schedule.json':raw['schedule_sha256'],'assignment.json.gz':raw['assignment_sha256']}
    assert sha(schedule)==files['schedule.json'] and sha(assignment)==files['assignment.json.gz']
    doc=read(schedule);cfg=doc['config'];d=scores(doc)
    assert cfg['chamber_residency_basis']=='nonprocessing' and cfg['module_residency']==cfg['robot_residency']==100
    assert cfg['dummy_count']==8 and cfg['horizon']==100000 and cfg['source']=='dual'
    assert (cfg['full_time'],cfg['mix_time'],cfg['cleaning_time'])==(180,90,500)
    if verify:
        check=validate(doc);assert check['valid'],check['errors']
    rows=raw['rows'] if 'rows' in raw else raw['replayed_rows']
    assert rows and raw['replay']['valid']
    return d|dict(schedule_path=rel(schedule),assignment_path=rel(assignment),schedule_sha256=sha(schedule),
                  assignment_sha256=sha(assignment),certificate=rel(cert),certificate_sha256=sha(cert),native_rows=rows,
                  configuration_sha256=hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest())


def origins():
    a={};b={};free={}
    for row in load_csv(OLD/'table4_seeds.csv'):
        if row['level']!='1':continue
        key=tuple(int(row[k]) for k in ('n','H','seed'))
        if row['arm']=='A':
            base=JMS/row['source'];a[key]=base,base/'primary.json',base/'primary.json'
        elif row['arm']=='AB':
            base=(JMS/row['source']).parent/'B';b[key]=base,base/'result.json'
    for row in load_csv(OLD/'free_B_shortest_verified.csv'):
        key=(int(row['n']),int(row['H']))
        if key[0]==4:
            base=JMS/f'results/pareto_scales_20261125/four_native_H{key[1]}/417_pinned'
            free[key]=base,base/'result.json'
        else:free[key]=(JMS/row['source']).parent,JMS/row['qualified_by']
    for row in read(EXT/'publication.json')['records']:
        h=row['H'];key=(16,h,row['seed']);base=(JMS/row['schedule_path']).parent
        if row['arm']=='A':a[key]=base,base/'primary.json',JMS/row['certificate']
        elif row['arm']=='AB':b[key]=base,JMS/row['certificate']
        else:free[16,h]=base,JMS/row['certificate']
    return a,b,free


def prepare():
    a,b,free=origins();records=[];needs=[]
    for n,h in CASES:
        base,cert=free[n,h];q=replay(base,cert);lb=lower_bound(n,h)
        assert (n,h)==(q['n'],q['H']) and abs(q['f_B']-lb['analytic_lower'])<1.e-6 and abs(q['spread']-lb['a'])<1.e-6
        records.append(q|lb|dict(seed=None,arm='B',lower=lb['analytic_lower'],method='Global chain-terminal bound, minimized over the unrestricted quadratic; feasible witness attains equality.'))
        for s in SEEDS:
            key=n,h,s
            base,cert,gate=a[key];av=replay(base,cert);raw=read(gate);abound=raw['lower'] if n==16 else raw['record']['lower']
            assert (n,h)==(av['n'],av['H']) and av['f_A']<=abound*1.01+TOL
            records.append(av|dict(seed=s,arm='A',lower=abound,gate=rel(gate),gate_sha256=sha(gate),method='Archived makespan-only endpoint; all process metrics recalculated.'))
            old,proof=b[key];prev=read(proof);rv=replay(old,proof)
            assert prev['seed']==s and prev['mode']=='fixed' and prev['target_gap']==.01 and prev['eligible']
            par=prev['parents'][0];assert par['schedule_sha256']==av['schedule_sha256'] and par['assignment_sha256']==av['assignment_sha256']
            assert abs(rv['f_A']-av['f_A'])<2.e-5
            lower=prev['record']['lower']
            if lower-TOL<=rv['f_B']<=1.01*lower+1.e-7:
                records.append(rv|dict(seed=s,arm='AB',parent=av['schedule_sha256'],lower=lower,
                    method='The prior global lower bound on this fixed structure remains valid since the new quadratic dominates the former penalty. The verified schedule meets the one-percent gap.'))
            else:
                needs.append(dict(n=n,H=h,seed=s,source=rel(base),origin_schedule_sha256=av['schedule_sha256'],
                                  origin_assignment_sha256=av['assignment_sha256'],fixed_huber_endpoint=rel(old),
                                  key=f'n{n}_H{h}_s{s}',prior_native_seconds=prev['record']['wall_seconds']))
    OUT.mkdir(exist_ok=True,parents=True)
    write(OUT/'verified_reuse.json',records);write(OUT/'jobs.json',needs)
    print(f'{len(records)} verified endpoints; {len(needs)} new fixed-structure solves required.',flush=True)
    return needs


def publish():
    jobs=prepare();records=read(OUT/'verified_reuse.json')
    for j in jobs:
        folder=OUT/'runs'/j['key'];proof=folder/'result.json';r=read(proof);v=replay(folder,proof)
        assert r['objective']=='mean_plus_spread_squared_over_2delta_plus_gamma_E_v1' and r['delta_s']==1
        assert r['eligible'] and r['mode']=='fixed' and r['seed']==j['seed'] and r['target_gap']==.01
        assert r['parents'][0]['schedule_sha256']==j['origin_schedule_sha256'] and r['parents'][0]['assignment_sha256']==j['origin_assignment_sha256']
        assert v['n']==j['n'] and v['H']==j['H']
        lb=r['record']['lower'];assert abs(v['f_B']-r['record']['upper'])<.00021
        assert lb<=v['f_B']+.00021 and v['f_B']<=lb*1.01+.00021
        records.append(v|dict(seed=j['seed'],arm='AB',parent=j['origin_schedule_sha256'],lower=lb,method='Native solve with the global quadratic range penalty.'))
    rows=[]
    for n,h in CASES:
        line={'n':n,'H':h}
        for arm in ('A','B','AB'):
            found=[v for v in records if (v['n'],v['H'],v['arm'])==(n,h,arm)]
            assert len(found)==(1 if arm=='B' else 3)
            for k in ('f_A','f_B'):line[f'{arm}_{k}']=statistics.mean(v[k] for v in found)
        rows.append(line)
    write(OUT/'publication.json',dict(objective='mean + within-recipe maximum spread squared / (2 s) + 1 s times unused pre-clean cycles',
          scale_s=1,gamma_s=1,thresholds={'A':.01,'AB':.01},seeds=SEEDS,rows=rows,records=records,
          counts=dict(primary_rescored=21,global_process_witnesses=7,fixed_by_bound_transfer=21-len(jobs),new_native_fixed=len(jobs)),
          published_inputs_sha256={p.name:sha(p) for p in (OUT/'jobs.json',OUT/'verified_reuse.json',HERE/'publish.py')}))
    with (OUT/'table4_rows.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    (prepare if '--prepare' in sys.argv else publish)()
