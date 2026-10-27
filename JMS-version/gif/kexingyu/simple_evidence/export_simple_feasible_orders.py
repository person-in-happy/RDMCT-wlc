"""Large, start-sorted handling-only export with proven identity substitution.

All times and resource choices stay fixed. Product identities can be permuted
because recipes are pure, every pair contains at most one product, and every
cross-product LP-to-LP interval meets the worst-case travel requirement.
"""
from pathlib import Path
from collections import defaultdict
from itertools import combinations
from datetime import datetime,timezone
import argparse,copy,gzip,hashlib,json,math,shutil,sys,time
from export_feasible_action_orders import ROOT,display,encoded,permutation_at,sha,audit_projection
from validate import validate


def product_order(data):
    return [e['job'] for e in sorted(data['events'],key=lambda e:e['start']) if e['kind']=='origin_pick']


def certify_substitution(data):
    audit=audit_projection(data)
    ids=product_order(data);products={j['identity'] for j in data['jobs'] if j['product']}
    if len(ids)!=len(products) or set(ids)!=products:raise ValueError('Product order is not a bijection')
    modes={p['mode'] for p in data['pairs'] if any(w in products for w in p['members'])}
    if len(modes)!=1:raise ValueError('Only pure recipes are covered by this substitution proof')
    if any(sum(w in products for w in p['members'])>1 for p in data['pairs']):raise ValueError('Two-product pair label normalization is outside this proof')
    if data['config']['source']!='dual':raise ValueError('Only the audited dual-source construction is supported')
    origins=[e for e in data['events'] if e['robot']=='ATR' and e['location'].startswith('LP')]
    gaps=[]
    for a,b in combinations(origins,2):
        if a['job']==b['job']:continue
        if a['start']>b['start']:a,b=b,a
        gaps.append(b['start']-a['end'])
    minimum=min(gaps)
    if minimum<data['config']['atr_travel']:raise ValueError('LP relabeling could violate robot travel')
    return dict(base_physical_audit=audit,minimum_cross_product_lp_gap=minimum,
        required_worst_case_lp_travel=data['config']['atr_travel'],
        theorem='pure_recipe_bijection_single_product_pairs_and_worst_case_LP_travel_v1',
        scope='All time/resource/cycle decisions unchanged; only product identities and their LP endpoints are substituted.')


def substitute(data,new_order):
    old=product_order(data)
    if len(new_order)!=len(old) or set(new_order)!=set(old):raise ValueError('Not a product bijection')
    mapping=dict(zip(old,new_order));result=copy.deepcopy(data)
    for pair in result['pairs']:pair['members']=[mapping.get(w,w) for w in pair['members']]
    for job in result['jobs']:
        if job['product']:
            job['name']=mapping[job['name']];job['identity']=mapping[job['identity']]
            job['origin']=job['identity'].split('_W')[0]
    for event in result['events']:
        if event.get('job') in mapping:
            event['job']=mapping[event['job']];event['name']=event['job']+'_'+event['kind']
            if event['location'].startswith('LP'):event['location']=event['job'].split('_W')[0]
    result['validation']=validate(result)
    if not result['validation']['valid']:raise ValueError(result['validation']['errors'])
    return result


def abstract_handling(data):
    order=product_order(data);positions={w:i for i,w in enumerate(order)}
    jobs={j['name']:j for j in data['jobs']};pairs={p['id']:p for p in data['pairs']}
    def token(w):return ('P',positions[w]) if w in positions else ('A',w)
    groups=defaultdict(list)
    for event in data['events']:
        if event['robot'] not in ('ATR','VTR'):continue
        if 'pair' in event:
            members=tuple(token(w) for w in pairs[event['pair']]['members'])
            action='put' if event['kind']=='pair_load' else 'pick'
        else:
            members=(token(jobs[event['job']]['identity']),)
            action='pick' if event['kind'] in ('origin_pick','source_pick','al_pick','lower_pick') else 'put'
        location=('LP',positions[event['job']]) if event['location'].startswith('LP') else ('fixed',event['location'])
        groups[event['start']].append((event['robot'],action,members,location))
    # Equal starts remain one group; no arbitrary ordering is counted within it.
    return [sorted(value) for _,value in sorted(groups.items())]


def render(groups,order):
    labels=[display(w) for w in order];ports=[w.split('_W')[0] for w in order]
    locations={'U':'LL上层','L':'LL下层','VS':'PECstorage','AS':'AS'}
    lines=[]
    for group in groups:
        entries=[]
        for robot,action,members,location in group:
            wafers='+'.join(labels[value] if kind=='P' else display(value) for kind,value in members)
            place=ports[location[1]] if location[0]=='LP' else locations.get(location[1],location[1])
            entries.append(wafers+' '+robot+('取 ' if action=='pick' else '放 ')+place)
        entries.sort()
        lines.append(entries[0] if len(entries)==1 else '{ '+' || '.join(entries)+' }')
    return ' -> '.join(lines)


def load_templates(base,n):
    manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    entry=next(row for row in manifest['files'] if row['n']==n)
    source=base/entry['witnesses']
    if sha(source)!=entry['witness_sha256']:raise ValueError('Original witness hash changed')
    templates={};checked=set()
    with gzip.open(source,'rt',encoding='utf-8') as stream:
        for line in stream:
            record=json.loads(line);data=record['witness'];groups=abstract_handling(data)
            key=hashlib.sha256(encoded(groups).encode('utf-8')).hexdigest();case=record['case']
            if (key,case) in checked:continue
            proof=certify_substitution(data);checked.add((key,case))
            if key not in templates:templates[key]=dict(groups=groups,cases=[],witnesses={},proofs={})
            templates[key]['cases'].append(case);templates[key]['witnesses'][case]=data;templates[key]['proofs'][case]=proof
    return list(templates.values()),dict(path=str(source),sha256=sha(source),audited_template_configuration_pairs=len(checked))


def run(args):
    base=Path(args.directory).resolve()
    if not base.is_relative_to(ROOT/'JMS-version/gif/kexingyu'):raise ValueError('Use the requested JMS-version/gif/kexingyu directory')
    evidence=base/'simple_evidence'
    if evidence.exists():raise ValueError('Preserve existing simple export; evidence already exists')
    evidence.mkdir()
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    manifest=dict(created_utc=datetime.now(timezone.utc).isoformat(),complete_enumeration=False,all_feasible_orders=None,
        counting='Handling actions only, sorted by start; exact simultaneous-start groups preserved; global dedup across four configurations.',
        validation='Every abstract template/configuration physically replayed; every output uses a bijection preserving constraints under recorded substitution proof; representative substitutions additionally replayed.',
        generator_sha256=sha(Path(__file__)),files=[])
    for n,count in zip((8,16,32),args.counts):
        started=time.monotonic();templates,origin=load_templates(base,n)
        ids=[f'LP{lp}_W{w}' for lp in range(1,5) for w in range(1,n//4+1)];total=math.factorial(n)
        if not 1<=count<=total:raise ValueError('Count must be between 1 and N!')
        # Check actual remapped full witnesses as well as the transformation proof.
        replay_count=0
        for template in templates:
            for case,data in template['witnesses'].items():
                for rank in (0,total//2,total-1):
                    substitute(data,permutation_at(ids,rank));replay_count+=1
        template_path=evidence/f'{n}wafer-templates.json.gz'
        with gzip.open(template_path,'wt',encoding='utf-8') as stream:json.dump(templates,stream,ensure_ascii=False,separators=(',',':'))
        path=base/f'{n}wafer-{count}种可行排程_简化取放_总数未知.txt'
        if path.exists():raise ValueError('Existing output '+str(path))
        index_path=evidence/f'{n}wafer-index.jsonl.gz';unique=set();case_counts=defaultdict(int);action_min=10**9;action_max=0
        header=(f'{n}片产品：本文件{count}种不同的简化取放序列；全部可行排程总数未知。\n'
            '仅保留晶圆、ATR/VTR取放与位置，按动作开始时间排序；同刻动作以{... || ...}合并。\n'
            '隐藏时间数值、动作结束、旋转、加工与清洁曝光；这些仍保留在可重建的完整时间证据中。\n'
            '包含全部产品和实际使用辅助片的取放，也包含末端清洁所需的取放。PEC1=模型辅助片D1。\n'
            '双源、两腔、8片辅助片、4个LP均分；四组配置为纯4x1/2x2与H=3/10。每条标题列适用配置。\n'
            '本文件为扩大后的可行子集，不是全空间枚举。不同规模的输出条数是导出配额，不能作空间大小比较。\n'
            '可行性依据：已验解模板+保持约束的产品身份双射；不是对每条重新运行MILP，也不是最优性认证。\n'
            '读取某条完整时间见证的方法和验证范围见README_简化版.md与simple_manifest.json。\n\n')
        with path.open('wb') as stream,gzip.open(index_path,'wt',encoding='utf-8') as index:
            stream.write(header.encode('utf-8-sig'))
            for i in range(count):
                rank=0 if count==1 else i*(total-1)//(count-1)
                order=permutation_at(ids,rank)
                if len(set(order))!=n or set(order)!=set(ids):raise RuntimeError('Not a bijection')
                template=templates[i%len(templates)];text=render(template['groups'],order)
                digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
                if digest in unique:raise RuntimeError('Duplicate simplified sequence')
                unique.add(digest);offset=stream.tell();action_count=sum(len(group) for group in template['groups'])
                action_min=min(action_min,action_count);action_max=max(action_max,action_count)
                record=f'[{i+1:06d}] 配置={",".join(template["cases"])} | 取放动作数={action_count}\n{text}\n\n'
                raw=record.encode('utf-8');stream.write(raw)
                index.write(encoded(dict(id=i+1,offset=offset,bytes=len(raw),template=i%len(templates),
                    permutation_rank=str(rank),sequence_sha256=digest))+'\n')
                for case in template['cases']:case_counts[case]+=1
                if (i+1)%1000==0 or i+1==count:
                    elapsed=time.monotonic()-started;eta=elapsed/(i+1)*(count-i-1)
                    print(f'n={n} written={i+1}/{count} failed=0 elapsed={elapsed:.1f}s ETA~{eta:.1f}s',flush=True)
        manifest['files'].append(dict(n=n,path=path.name,count=len(unique),all_feasible_orders=None,sha256=sha(path),bytes=path.stat().st_size,
            templates=str(template_path.relative_to(base)),templates_sha256=sha(template_path),template_count=len(templates),
            index=str(index_path.relative_to(base)),index_sha256=sha(index_path),source=origin,
            per_configuration=dict(case_counts),action_count_range=[action_min,action_max],
            additional_full_witness_replays=replay_count,product_order_lower_bound=str(total),
            permutation_rank_selection='All ranks for N=8; evenly spaced ranks for larger N.',elapsed_seconds=time.monotonic()-started))
        (base/'simple_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print('FINISHED '+path.name,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--directory',default='JMS-version/gif/kexingyu')
    parser.add_argument('--counts',nargs=3,type=int,default=[40320,50000,60000])
    run(parser.parse_args())
