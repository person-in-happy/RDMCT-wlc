"""Copy already enumerated admissible sequences; replay representative schedules."""
from pathlib import Path
from collections import Counter
import gzip, hashlib, json, re, sys
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
NEW=ROOT/'JMS-version/model4_pjob_fifo_20261029'
sys.path.insert(0,str(NEW))
from model import Config
from validate import validate as strict_validate
from pjob_order import encoding,order_report
from audit_existing import plan_lps
# Reuse the deterministic composition of immutable, prevalidated physical blocks.
sys.path.insert(0,str(ROOT/'JMS-version/tools'))
from model4_feasible_orders import compose,unrank_plan

OLD=ROOT/'JMS-version/gif/kexingyu/model4_pjob_20261027'
OUT=ROOT/'JMS-version/gif/kexingyu/pjob_fifo_20261029'
OUT.mkdir(exist_ok=False)
(OUT/'evidence').mkdir();(OUT/'examples').mkdir()
audit=json.loads((HERE/'strict_order_audit.json').read_text('utf-8'))
with gzip.open(OLD/'evidence/blocks.json.gz','rt',encoding='utf-8') as stream:blocks=json.load(stream)
manifest=dict(release_rule='global_pjob_index_strict_lp_pickup',solver_runs=0,
              source='Filtered existing sequences, unchanged physical action times',sizes={},examples=[])
for n in (8,16,32):
    filename=f'{n}wafer_pjob_strict_orders.txt'
    source=next(OLD.glob(f'*_{n}wafer_*.txt'))
    rows=[]
    with source.open('rb') as original,(OUT/filename).open('wb') as target:
        target.write((f'{n}片产品晶圆；同一Pjob严格按批次内序号取片。\n'
                      '下列动作序列筛自既有记录，数值排程未调整。\n\n').encode('utf-8'))
        with gzip.open(OLD/f'evidence/{n}wafer-index.jsonl.gz','rt',encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line);lps=plan_lps(n,int(row['rank']))
                if max(i for i,lp in enumerate(lps) if lp==3)>min(i for i,lp in enumerate(lps) if lp==4):continue
                count=Counter();codes=[];numbers=[]
                for lp in lps:
                    task=lp if lp<3 else 3;count[task]+=1
                    codes.append(f'Pjob{task}[{count[task]}]')
                    slot=count[task] if lp<4 else count[task]-n//4
                    numbers.append(25*(lp-1)+slot)
                original.seek(row['offset']);text=original.read(row['bytes']).decode('utf-8')
                text=re.sub(r'^\[\d+\]',f'[{len(rows)+1:06d}]',text,count=1)
                text=('编码出片：'+' -> '.join(codes)+'\n实际晶圆：'+','.join(map(str,numbers))+'\n'+text)
                offset=target.tell();content=text.encode('utf-8');target.write(content)
                rows.append(row|dict(id=len(rows)+1,source_id=row['id'],offset=offset,bytes=len(content)))
    assert len(rows)==audit['construction'][str(n)]['retained']
    assert len({r['sequence_sha256'] for r in rows})==len(rows)
    with gzip.open(OUT/f'evidence/{n}wafer-index.jsonl.gz','wt',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    manifest['sizes'][str(n)]=dict(count=len(rows),per_recipe=dict(Counter(r['recipe'] for r in rows)),
        lower_bound_per_configuration=audit['construction'][str(n)]['lower_bound_per_config'],
        file=filename,sha256=hashlib.sha256((OUT/filename).read_bytes()).hexdigest())
    for recipe,examples in audit['construction'][str(n)]['examples'].items():
        for index,row in enumerate(examples):
            for h in (3,10):
                data=compose(blocks[recipe],unrank_plan(n,int(row['rank'])),h)
                data['config']['pjobs']=[dict(id=f'Pjob{j}',mode=recipe,chambers=[2] if j==1 else [3] if j==2 else [2,3],
                    wafers=[job['identity'] for job in data['jobs'] if job['product'] and job['pjob']==f'Pjob{j}']) for j in (1,2,3)]
                cfg=Config(**data['config']);codes=encoding(cfg)
                data['product_encoding']=codes;data['model_scope']='pjob_global_fifo_constructive_witness'
                for job in data['jobs']:
                    if job['product']:job.update(codes[job['identity']])
                data['validation']=strict_validate(data)
                assert data['validation']['valid'],data['validation']['errors']
                name=f'n{n}_{recipe}_H{h}_example{index+1}.json'
                (OUT/'examples'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')
                manifest['examples'].append(dict(file='examples/'+name,cmax=data['cmax'],validation=data['validation']))
    print(f'{n} wafers: retained={len(rows)}, representative replay valid',flush=True)
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
print('Completed:',len(manifest['examples']),'representative schedules, no solver run',flush=True)
