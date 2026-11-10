"""Summarize saved evidence, without optimization or modifying source data."""
from pathlib import Path
import json, hashlib
from collections import Counter
from inventory import ROOT, OUT, walk

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def model_of(p, spec):
    s=json.dumps(spec,ensure_ascii=False).replace('\\\\','/').replace('\\','/')
    for token,label in [('model4_pjob_nonprocessing_20261103','M4-D'),('model4_pjob_nondecreasing_20261102','M4-E'),('model4_pjob_fifo_20261029','M4-FIFO'),('model4_pjob_20261027','M4-group'),('heterogeneous_model_20261022','M3'),('model2_lowmem_20261026','M2-lowmem'),('model2_compact_20261025','M2-compact'),('joint_model','M2')]:
        if token in s:return label
    n=p.name
    if n.startswith('joint_model'):return 'M2 historical (subcampaigns differ)'
    if n.startswith(('current_defaults','review_d_','gap_d_')):return 'M4-D (directory inference)'
    if n.startswith('nondecreasing_') or n.startswith('pjob_nondecreasing_'):return 'M4-E (directory inference)'
    if n.startswith(('pjob_fifo_','review_','strengthen_')):return 'M4-FIFO (directory inference)'
    if n.startswith('model4_'):return 'M4-group (directory inference)'
    if 'heterogeneous100' in n:return 'M3'
    if n.startswith(('optional_cleaning','supp_','paper_','optimality_')):return 'M2 (directory inference)'
    if n.startswith('wafer'):return 'M1 historical fixed structure'
    return 'unclassified / support'

def main():
    catalog=[]
    for p in sorted((ROOT/'JMS-version/results').iterdir()):
        if not p.is_dir():continue
        spec=read(p/'campaign.json') if (p/'campaign.json').exists() else {}
        cv=p/'summary/coverage.json'
        coverage=read(cv) if cv.exists() else {}
        cells=p/'summary/cells.json'
        rows=read(cells) if cells.exists() else []
        if isinstance(rows,dict):rows=rows.get('cells',rows.get('rows',[]))
        for row in rows:
            if not row.get('state'):
                row['state']=row.get('execution',row.get('status','unreported'))
            ep=p/'runs'/row.get('id','')/'evidence.json'
            if 'valid' not in row and ep.exists():
                e=read(ep)
                row['valid']=e.get('valid',False)
        if not rows and spec.get('cells') and (p/'runs').exists():
            for cell in spec['cells']:
                rp=p/'runs'/cell['id']/'result.json'
                if rp.exists():
                    d=read(rp)
                    rows.append({'id':cell['id'],'state':d.get('primary_status',d.get('status')),'valid':bool(d.get('solutions') and d.get('validation',{}).get('valid') and d.get('original_model_check')),'arm':cell.get('method',cell.get('arm'))})
                else:
                    fp=rp.parent/'failure.json'
                    rows.append({'id':cell['id'],'state':'execution_failed' if fp.exists() else 'pending','valid':False})
        cfg=[]
        for q in sorted((p/'configs').glob('*.json'))[:2] if (p/'configs').exists() else []:
            d=read(q);cfg.append({k:d.get(k) for k in ['load_ports','module_residency','robot_residency','horizon','cleaning_interval','full_time','mix_time','dummy_count','chamber_residency_mode'] if k in d})
        rec={'campaign':str(p.relative_to(ROOT)).replace('\\','/'),'model':model_of(p,spec),'coverage':coverage,'summary_rows':len(rows),'states_from_summary':dict(Counter(str(r.get('state',r.get('status'))) for r in rows)),'valid_true_in_summary':sum(r.get('valid') is True for r in rows),'variants':dict(Counter(str(r.get('variant',r.get('arm'))) for r in rows)),'config_examples':cfg,'settings':spec.get('settings',{k:spec[k] for k in ['suite','time_limit','seeds','memory_mb','spbs_budget','cut_profile','training_seed','scope'] if k in spec}),'saved_finished':read(p/'finished.json') if (p/'finished.json').exists() else None,'source_hashes':{str(q.relative_to(ROOT)).replace('\\','/'):sha(q) for q in [p/'campaign.json',cv,cells] if q.exists()}}
        catalog.append(rec)
    cie=[]
    for p in sorted((ROOT/'cie/results').glob('*/*/submission_analysis/submission_audit.json')):
        d=read(p); files=[Path(f) for f in d['csv_files']]; n=0; statuses=Counter()
        import csv
        for f in files:
            if f.exists():
                rr=list(csv.DictReader(f.open(encoding='utf-8-sig',newline='')));n+=len(rr);statuses.update(r.get('status','') for r in rr)
        cie.append({'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sha(p),**{k:d.get(k) for k in ['stage','expected_rows','csv_rows','jsonl_rows','incumbent_rows','issues','ok']},'source_csv_rows_now':n,'source_csv_files_missing':sum(not f.exists() for f in files),'statuses_now':dict(statuses)})
    extra={}
    for s in ['JMS-version/results/joint_model','T-ASE-version/results','RL-SAT/results','JMS/results/mode_cleaning_crossover']:
        p=ROOT/s
        extra[s]=[str(q.relative_to(ROOT)).replace('\\','/') for q in walk(p) if q.name in ['coverage.json','records.json','run_summary.json','mode_cleaning_crossover.json','certificate.json']]
    (OUT/'campaign_catalog.json').write_text(json.dumps({'jms':catalog,'cie':cie,'other_evidence':extra},ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 实验批次全索引（2026-11-08）','','由 `catalog.py` 只读生成。状态来自保存的汇总/逐单元结果；不是本次重新验解。目录推断已注明。计数为运行记录，不能当作独立实例数。汇总行可能包括待跑单元或参考检查，不能直接当作求解次数；valid=true为保存的检查标记，0也可能表示缺少该字段。没有汇总不代表没有结果；见 inventory.json 的文件索引。','','| 模型 | 批次（JMS-version/results/） | 汇总行数 | 状态计数 | 保存的 valid=true |','|---|---|---:|---|---:|']
    for r in catalog:
        lines.append('| '+r['model']+' | `'+Path(r['campaign']).name+'` | '+str(r['summary_rows'])+' | '+json.dumps(r['states_from_summary'],ensure_ascii=False)+' | '+str(r['valid_true_in_summary'])+' |')
    lines+=['','## CIE原始CSV与保存审计核对','','| 阶段 | 计划 | 保存审计行数 | 本次实际CSV行数 | incumbent | 审计通过 |','|---|---:|---:|---:|---:|---|']
    for r in cie:lines.append(f"| {r['stage']} | {r['expected_rows']} | {r['csv_rows']} | {r['source_csv_rows_now']} | {r['incumbent_rows']} | {r['ok']} |")
    (OUT/'CAMPAIGN_CATALOG_CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Catalog saved:',len(catalog),'JMS campaign directories;',len(cie),'CIE stages; actual CSV rows',sum(r['source_csv_rows_now'] for r in cie))

if __name__=='__main__':main()
