"""Recompute manuscript-table pairings from individual results, without editing the manuscript."""
import argparse
from collections import defaultdict
import csv
from functools import lru_cache
from pathlib import Path
from statistics import mean
import subprocess
import sys
import time

from protocol import HERE,LEVELS,OUT,POLICIES,RESULTS,ROOT,SEEDS,TUNING,read,rel,save,sha
from design import pick
sys.path.insert(0,str(HERE.parent/'finite_budget_20261116'))
from finite_budget import BACKENDS,physical_metrics

NAMES={'certified-grid':'两阶段间隙扰动','certified-spbs':'初始化消融与进入搜索前的工期',
       'certified-cuts':'相同阈值下的选割消融','joint-two-stage':'联合权重与两阶段求解',
       'refinement-ablation':'第二阶段消融','rhythm-weight':'腔室节拍权重扰动',
       'structure-ablation':'总驻留约束下的结构消融','journal-structure':'非加工驻留约束下的结构消融',
       'journal-algorithm':'有无初始化的算法对比','journal-transfer':'供片场景与选割对照'}
METHOD_NAMES={'hem_spbs':'HEM','feature_only':'仅扩展特征','no_rerank':'关闭重排','greedy':'贪心解码',
              'full':'完整学习选割','default':'SCIP 默认'}


def close(a,b):
    if abs(a-b)>2e-4: raise ValueError(f'{a} differs from {b}')


@lru_cache(maxsize=None)
def frozen_digest(path):
    return sha(path)


def output_csv(name,rows):
    if not rows:return
    path=OUT/name
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.with_suffix('.tmp').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    path.with_suffix('.tmp').replace(path)


def verify_pairings(tasks):
    expected_csv={
        'all_cells.csv':len(tasks),
        'objective_pairs.csv':sum(t['kind']=='weighted' for t in tasks.values()),
        'rhythm_weights.csv':sum('rhythm-weight' in t['tables'] for t in tasks.values()),
        'refinement_pairs.csv':sum('refinement-ablation' in t['tables'] and t['kind']=='secondary' for t in tasks.values()),
        'structure_cells.csv':sum('__structure_' in k and 'prefix' not in k for k in tasks),
        'component_pairs_with_original.csv':sum(t['kind']=='scip' for t in tasks.values()),
        'certified_original_pairs.csv':len(TUNING)*len(POLICIES),
    }
    matched_archive=0
    objective_eligible=0
    for name,expected in expected_csv.items():
        with (OUT/name).open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.DictReader(handle))
        if len(rows)!=expected:raise ValueError('Incomplete table '+name)
        if name=='component_pairs_with_original.csv':
            if any(not r.get('reference_file') or not r.get('cp_cmax') for r in rows):raise ValueError('Missing paired control')
            matched_archive=sum(r['input_values_match_archive']=='True' for r in rows)
        if name=='objective_pairs.csv':objective_eligible=sum(r['eligible']=='True' for r in rows)
    return expected_csv,matched_archive,objective_eligible


def check_backend(family):
    sys.path.insert(0,str(BACKENDS[family]))
    from validate import validate
    spec=read(OUT/'protocol.json')
    if sha(OUT/'protocol.json')!=read(OUT/'contract.json')['sha256']:
        raise ValueError('Experiment registration changed')
    for source in spec['inputs'].values():
        if sha(ROOT/source['schedule'])!=source['schedule_sha256'] or sha(ROOT/source['assignment'])!=source['assignment_sha256']:
            raise ValueError('Registered starting point changed')
    counts={}
    selected_a=0
    for key,t in spec['tasks'].items():
        if t['backend']!=family:continue
        d=OUT/'runs'/key
        if not (d/'evidence.json').exists():continue
        e=read(d/'evidence.json')
        if (not e['valid'] or e['worker_sha256']!=spec['assets'][rel(HERE/'cell.py')]
            or sha(d/'schedule.json')!=e['schedule_sha256'] or sha(d/'assignment.json.gz')!=e['assignment_sha256']):
            raise ValueError('Unverified '+key)
        data=read(d/'schedule.json')
        result=validate(data)
        if not result['valid']:raise ValueError((key,result['errors'][:2]))
        for k,v in physical_metrics(data).items():close(v,e['metrics'][k])
        record=e['record']
        first=record.get('primary',record)
        policy=first.get('policy')
        if policy and (frozen_digest(policy['checkpoint'])!=policy['sha256'] or
                       frozen_digest(policy['config'])!=policy['config_sha256']):
            raise ValueError('Policy weights or configuration changed '+key)
        if t['kind'] in ('cp','scip'):
            close(record['upper'],e['metrics']['cmax'])
            close(record['gap'],max(0.,record['upper']-record['lower'])/record['lower'])
        if t['kind']=='secondary':
            physical=e['metrics']
            close(record['upper'],physical['wait_sum']+10*physical['wait_max']+t['weight']*physical['rhythm'])
            if physical['cmax']>e['initial']['cmax']+2e-4:raise ValueError('Secondary exceeded its cap '+key)
        if t['kind']=='weighted':
            scaling=record['normalization']
            close(record['upper'],e['metrics']['cmax']/scaling['cmax']+t['rho']*e['metrics']['secondary']/scaling['secondary'])
        source=spec['inputs'].get(t['start']) or read(OUT/'runs'/t['start']/'evidence.json')
        if e['input_sha256']!=source['assignment_sha256'] or e['source_sha256']!=source['schedule_sha256']:
            raise ValueError('Broken input chain '+key)
        if t['kind']=='secondary' and t['gap'] is not None and (not source['record']['gate'] or not e['record']['gate']):
            raise ValueError('Gap gate broken '+key)
        if t['kind']=='selected':
            stage=d/'A'
            evidence=read(stage/'evidence.json')
            if (evidence['input_sha256']!=e['input_sha256'] or sha(stage/'assignment.json.gz')!=evidence['assignment_sha256']
                or sha(stage/'schedule.json')!=evidence['schedule_sha256'] or evidence['record']!=e['record']['primary']
                or not evidence['record']['gate'] or not e['record']['secondary']['gate']):
                raise ValueError('Unverified selected first-stage solution '+key)
            stage_data=read(stage/'schedule.json')
            if not validate(stage_data)['valid']:raise ValueError('Selected first-stage replay failed '+key)
            for k,v in physical_metrics(stage_data).items():close(v,evidence['metrics'][k])
            if e['metrics']['cmax']>evidence['metrics']['cmax']+2e-4:raise ValueError('First-stage makespan exceeded '+key)
            selected_a+=1
        counts[key]=result['checks']
    extra={}
    if family=='D':
        scale=verify_scale()
        replay=validate(read(OUT/'scale75/result.json'))
        if not replay['valid'] or replay['checks']!=scale['replay']['checks']:raise ValueError('75-wafer replay mismatch')
        extra['scale75_checks']=replay['checks']
    save(OUT/f'replay_{family}.json',dict(cells=len(counts),checks=sum(counts.values()),by_cell=counts,selected_A=selected_a,**extra))
    print(f'{family}: {len(counts)} schedules independently replayed')


def verify_complete(replay_again=True):
    final=read(OUT/'completion.json')
    if final['expected']!=final['completed'] or final['failed'] or final['dependent_pending']:
        raise ValueError('The main campaign has unfinished cells')
    build()
    table_data=read(OUT/'table_status.json')
    if table_data['missing'] or any(v['expected']!=v['complete'] for v in table_data['by_table'].values()):
        raise ValueError('Incomplete manuscript table coverage')
    spec=read(OUT/'protocol.json')
    expected_csv,matched_archive,objective_eligible=verify_pairings(spec['tasks'])
    for name,expected in spec['assets'].items():
        if sha(ROOT/name)!=expected:raise ValueError('Changed registered solver asset '+name)
    if replay_again:
        for family in ('D','E'):
            subprocess.run([sys.executable,'-B','-X','utf8',str(Path(__file__).resolve()),'--replay',family,'--replay-only'],check=True)
    replays=[read(OUT/f'replay_{family}.json') for family in ('D','E')]
    if sum(r['cells'] for r in replays)!=len(spec['tasks']):raise ValueError('Incomplete replay')
    from spbs_control import DEST,pairing,specification
    extra=specification()
    if read(DEST/'protocol.json')!=extra or sha(DEST/'protocol.json')!=read(DEST/'contract.json')['sha256']:
        raise ValueError('Changed initialization control protocol')
    pairing(extra)
    controls=read(DEST/'comparison.json')
    drawings=read(OUT/'figures/index.json')
    for size,f in drawings.items():
        if sha(ROOT/f['source'])!=f['schedule_sha256']:raise ValueError('Figure schedule has changed')
        for ext,digest in f['files'].items():
            if sha(OUT/'figures'/size/('gantt.'+ext))!=digest:raise ValueError('Figure file has changed')
    if set(drawings)!={'n2','n16','n75'}:raise ValueError('Missing manuscript figure')
    main_tex_digest=sha(ROOT/spec['manuscript'])
    save(OUT/'verification.json',dict(main_cells=final['completed'],all_tables_complete=True,extra_spbs_stages=controls['tasks'],
          main_final_replay_checks=sum(r['checks'] for r in replays),additional_selected_A=sum(r['selected_A'] for r in replays),
          extra_spbs_replay_checks=controls['independent_replay_checks'],scale75_replay_checks=replays[0]['scale75_checks'],
          scale75_original_rows=verify_scale()['original_rows'],figure_files=sum(len(v['files']) for v in drawings.values()),
          csv_rows=expected_csv,archive_matched_primary_inputs=matched_archive,joint_eligible_pairs=objective_eligible,
          registered_manuscript_sha256=spec['manuscript_sha256'],current_manuscript_sha256=main_tex_digest,
          manuscript_matches_registration=main_tex_digest==spec['manuscript_sha256']))
    build()


def case_name(k):
    c=SPEC['cases'][k]
    mix=c['mix']
    modes='混合' if all(mix.values()) else ('4×1' if mix.get('4x1') else '2×2')
    layout=k.split('scenario')[-1] if 'scenario' in k else ('同LP' if 'sameLP' in k else '跨LP' if 'crossLP' in k else '')
    if layout.isdigit():layout='S'+layout
    family='总驻留' if c['backend']=='E' else '非加工驻留'
    return f"{c['n']}片 {modes} {layout} H{c['config']['cleaning_interval']} {'单源' if c['config']['source']=='single' else '双源'} {family}".replace('  ',' ')


def table(headers,entries):
    return ['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |',
            *['| '+' | '.join(str(x) for x in row)+' |' for row in entries],'']


def num(x,d=2):
    return ('—' if x is None else f'{x:.{d}f}'.rstrip('0').rstrip('.') if d else str(round(x)))


def verify_scale():
    s=read(OUT/'scale75/evidence.json')
    cert=read(OUT/'scale75/original_row_audit/certificate.json')
    sched=read(OUT/'scale75/result.json')
    if (sha(OUT/'scale75/result.json')!=s['schedule_sha256'] or cert['result_sha256']!=s['schedule_sha256']
        or sha(OUT/'scale75/original_row_audit/assignment.json.gz')!=cert['assignment_sha256']
        or cert['status']!='all_original_rows_satisfied' or not s['valid']):raise ValueError('Invalid 75-wafer evidence')
    close(s['gap'],(s['upper']-s['lower'])/s['lower'])
    for k,v in physical_metrics(sched).items():close(v,s['physical'][k])
    if s['secondary_started']!=s['gate']:raise ValueError('Incorrect 75-wafer switch')
    return s


@lru_cache(maxsize=None)
def historic_cut(cell):
    t=SPEC['tasks'][cell]
    case=t['case'].removeprefix('D_')
    case={'n4_mixed_H10':'n4_H10_mixed_dual','n2_mixed':'n2_H3_mixed_dual',
          'n2_4x1_crossLP':'n2_H3_4x1_dual','n2_4x1_sameLP':'n2_H3_4x1_dual_same_lp'}.get(case,case)
    method={'default':'scip','hem_spbs':'hem','full':'proposed','no_rerank':'proposed_no_structure',
            'greedy':'proposed_greedy','feature_only':'feature_only'}[t['method']]
    suff='plain' if '__cut_plain_' in t['id'] else 'spbs'
    old=f"{case}__s{t['seed']}__t{t['train']}__{method}_{suff}"
    banks=['journal_d_transfer_20261109_r1'] if 'journal-transfer' in t['tables'] else [
        'journal_d_standard_t1_20261108_unlimited_r1','journal_d_backfill_standard_20261109_r1']
    for bank in banks:
        d=RESULTS/bank/'runs'/old
        if not (d/'evidence.json').is_file():continue
        e=read(d/'evidence.json')
        if not e['valid'] or sha(d/'result.json')!=e['result_sha256']:raise ValueError('Damaged original control')
        sched=read(d/'result.json')
        if sched['config']!=SPEC['cases'][t['case']]['config']:raise ValueError('Different reference configuration')
        cmax=physical_metrics(sched)['cmax']
        times=e.get('solve_seconds',sched.get('solve_seconds'))
        if e.get('shared_spbs_input'):
            assignment=Path(e['shared_spbs_input'])/'variables.json'
            if sha(assignment)!=e['shared_spbs_variables_sha256']:raise ValueError('Shared archive preparation changed')
        elif suff=='spbs':
            assignment=d/'spbs_variables.json'
        else:
            assignment=Path(e['cell']['values'])
        primary_hash=sha(assignment)
        if (e.get('shared_spbs_input') or suff=='plain') and primary_hash!=e['common_input_sha256']:
            raise ValueError('Archived primary input changed')
        return dict(reference_cmax=cmax,reference_file=rel(d/'evidence.json'),reference_sha256=sha(d/'evidence.json'),
                    reference_input=primary_hash,reference_input_file=rel(assignment),reference_seconds=times,
                    reference_budget_ok=(times is not None and times<=t['seconds']+1))
    return {}


@lru_cache(maxsize=None)
def assignment_difference(left,right):
    def sparse_values(name):
        value=read(ROOT/name)
        if 'values' in value:return value['values']
        if value['default']!=0:raise ValueError('Unsupported assignment default')
        return value['nonzero']
    x,y=sparse_values(left),sparse_values(right)
    return max((abs(x.get(v,0.)-y.get(v,0.)) for v in x.keys() | y.keys()),default=0.)


def fixed_table(all_e):
    rows=[]
    for key,e in all_e.items():
        t=SPEC['tasks'][key]
        record=e['record']
        budget=t.get('seconds')
        primary=record.get('primary',record)
        effort=primary.get('search',{})
        flat=dict(cell=key,case=t['case'],n=t['n'],table=','.join(t['tables']),kind=t['kind'],
                  seed=t['seed'],training_seed=t.get('train'),budget_s=budget,eligible=e['budget_eligible'],
                  objective_scope=record['scope'],cmax_s=e['metrics']['cmax'],secondary=e['metrics']['secondary'],
                  wait_sum=e['metrics']['wait_sum'],max_wait=e['metrics']['wait_max'],rhythm=e['metrics']['rhythm'],
                  rhythm_centers=e['metrics']['rhythm_centers'],solver_s=record['seconds'],wall_s=e['wall_s'],
                  lower=record.get('lower'),upper=record.get('upper'),gap=record.get('gap'),gate=record.get('gate'),
                  calls=primary.get('policy_calls'),lp_solves=effort.get('lp_solves'),lp_iterations=effort.get('lp_iterations'),
                  scip_nodes=effort.get('nodes'),cp_branches=effort.get('branches'),first_stage_s=primary.get('seconds') if t['kind'] in ('cp','scip','selected') else None,
                  first_stage_lower=primary.get('lower') if t['kind'] in ('cp','scip','selected') else None,
                  first_stage_upper=primary.get('upper') if t['kind'] in ('cp','scip','selected') else None,
                  stopped_on_initial_bound=primary.get('initial_proof'),candidate_passed_full_model=primary.get('accepted_candidate'),
                  over_nominal_s=None if budget is None else max(0.,record['seconds']-budget),
                  status=primary.get('status'),source_assignment=e['input_sha256'],
                  peak_rss_mib=e['peak_rss_mib'],file=rel(OUT/'runs'/key/'evidence.json'))
        rows.append(flat)
    return rows


def build():
    global SPEC
    SPEC=read(OUT/'protocol.json')
    tasks=SPEC['tasks']
    all_e={k:read(OUT/'runs'/k/'evidence.json') for k in tasks if (OUT/'runs'/k/'evidence.json').is_file()}
    scale=verify_scale()
    progress=read(OUT/'progress.json')
    document=['# 按文稿设计补跑的实验','','数据取自本轮独立目录。工期表示最后一片产品返回的时刻，单位为秒。第一阶段间隙分母为正的全局下界。固定时间预算实验按原表规定的时点交接，间隙实验只有达到工期门槛才能交接。','',
              f'2、4、16 片完成 {len(all_e)}/{len(tasks)} 个求解或准备任务。75 片另有一项混跑展示。各求解器单线程运行，小中规模最多 8 项并行，其中最多 2 项为 16 片。','',
              '本轮使用 Windows 11、Intel Core Ultra 7 265KF（20 个逻辑处理器）。投影工期搜索使用 Python 3.13.5 与 OR-Tools 9.15.6755。学习选割使用 Python 3.12.12 和 PyTorch 2.11.0 在 CPU 上推理。两套环境的 PySCIPOpt 均为 6.1.0，SCIP 均为 10.0.1。','',
              '## 文稿范围','']
    scope_notes={2:'双阈值、SPBS 与选割、结构搜索、算法与供片场景',4:'联合目标、第二阶段与结构消融、SPBS 与算法',16:'两种纯配方的联合目标与初始化、纯 2×2 的节拍权重'}
    document+=table(['规模','正文对应实验','主队列完成 / 计划'],[
                    [f'{n} 片',scope_notes[n],f"{sum(tasks[k]['n']==n for k in all_e)} / {sum(v['n']==n for v in tasks.values())}"]
                    for n in (2,4,16)]+[['75 片','双腔混合排程与全资源甘特图','1 / 1（单列）']])
    document+=table(['对应实验','已完成 / 计划任务数'],[(NAMES[t],f"{sum(t in tasks[k]['tables'] for k in all_e)} / {sum(t in row['tables'] for row in tasks.values())}") for t in SPEC['tables']])
    document+=['工期优先方案先用设备容量和已验证上界缩减候选，再由 CP-SAT 求工期界。每份可行排程须通过原连续模型和独立事件重放。学习选割的五项消融在同样缩减后的 SCIP 模型上执行，逐次记录实际调用。第二阶段的工艺目标按原表保留第一阶段的离散结构。',
               '', '下表及逐种子数据区分名义求解预算和包括建模、核验在内的实耗。固定预算均值沿用原表的 1 s 求解计时容差，上游阶段超时的配对也标记为超时。','']
    projections=[e['record'] for k,e in all_e.items() if tasks[k]['kind']=='cp']
    searched=[r for r in projections if not r.get('initial_proof')]
    if projections:
        document+=[f"主队列已完成 {len(projections)} 个独立投影工期单元，其中 {len(projections)-len(searched)} 个在起点已满足工期间隙要求。其余 {len(searched)} 个启动 CP-SAT 搜索，{sum(bool(r.get('accepted_candidate')) for r in searched)} 个返回的候选排程通过原模型回验。",'']
    document+=['## 两个 2 片实例的参数扰动','']
    grid={}
    entries=[]
    for c in TUNING:
        for a in LEVELS:
            first=all_e.get(f'{c}__grid_A_{a}')
            bs=[]
            for b in LEVELS:
                e=all_e.get(f'{c}__grid_B_{a}_{b}')
                if e:
                    grid[c,a,b]=e
                    bs.append(f"{num(e['metrics']['secondary'])}（{num(e['record']['gap']*100,4)}%）")
                else: bs.append('待完成')
            if first:
                entries.append([case_name(c),num(LEVELS[a]*100,2)+'%',num(first['metrics']['cmax']),num(first['record']['gap']*100,4)+'%',*bs])
    document+=table(['实例','切换阈值','工期','实际工期间隙','停机 10%','停机 1%','停机 0.01%'],entries)
    chosen=pick(grid)
    original_rows=[]
    if chosen:
        a,b=chosen
        document+=[f'按文稿的两实例等权、工期优先规则，选择切换阈值 {num(LEVELS[a]*100)}%、停机阈值 {num(LEVELS[b]*100)}%。括号内为实际工艺子问题间隙。','',
                   '## 初始化和选割消融','']
        entries=[]
        for c in TUNING:
            pa=all_e[f'{c}__grid_A_{a}']
            sb=grid[c,a,b]
            seconds_pre=SPEC['inputs'][c+'/cert_prep']['prep_seconds']
            entries.append([case_name(c),'CP-SAT，保留设备界与 SPBS',num(pa['metrics']['cmax']),num(sb['metrics']['secondary']),num(pa['record']['seconds']),num(seconds_pre+pa['wall_s']+sb['wall_s']), '不调用'])
            for key,label in [('selected_no_spbs','CP-SAT，省略 SPBS'),('selected_unreduced','CP-SAT，保留原候选容量'),
                              *[(f'selected_cut_{m}','缩减后 SCIP ＋ '+METHOD_NAMES[m]) for m in POLICIES]]:
                e=all_e.get(f'{c}__{key}')
                if e:
                    p=e['record']['primary']
                    entries.append([case_name(c),label,num(e['metrics']['cmax']),num(e['metrics']['secondary']),num(p['seconds']),
                                    num((0 if key=='selected_no_spbs' else seconds_pre)+e['wall_s']),p.get('policy_calls') if p.get('policy_calls') is not None else '不调用'])
            # Frozen original controls are kept individually so times and outcomes remain attributable.
            sys.path.insert(0,str(HERE.parent/'component_gap_restore_20261119'))
            from component import folders
            for method in POLICIES:
                oa,ob=folders(c,method)
                one,two=read(oa/'evidence.json'),read(ob/'evidence.json')
                if (not one['gate']['accepted'] or not two['gate']['accepted'] or
                    one['assignment_sha256']!=two['input_sha256'] or
                    one['input_sha256']!=SPEC['inputs'][c+'/cert_prep']['assignment_sha256'] or
                    sha(ob/'schedule.json')!=two['schedule_sha256']):raise ValueError('Archived gap controls do not pair')
                new=all_e.get(c+'__selected_cut_'+method)
                original_rows.append(dict(case=c,method=method,archival_A=rel(oa/'evidence.json'),archival_B=rel(ob/'evidence.json'),
                     common_start_sha256=one['input_sha256'],original_A_seconds=one['record']['seconds'],
                     original_Cmax=two['metrics']['cmax'],original_fB=two['metrics']['secondary'],
                     compact_scip_A_seconds=new['record']['primary']['seconds'] if new else None,
                     compact_scip_fB=new['metrics']['secondary'] if new else None,
                     projected_A_seconds=pa['record']['seconds'],projected_fB=sb['metrics']['secondary']))
        document+=table(['实例','方法','工期','固定结构工艺目标','第一阶段求解 s','含初始化与两阶段实耗 s','学习选割调用'],entries)
        output_csv('certified_original_pairs.csv',original_rows)
        document+=['纯 4×1 的初始工期已等于 324 s 的下界，五种学习策略的选割调用均为零。表中带 SPBS 的行计入实际共用的冻结初始化成本，独立复跑的初始化另列。原始模型在相同输入与阈值下的五种选割记录可逐组对照。[原模型与本轮配对](certified_original_pairs.csv)','']
        for r in original_rows:
            if r['method']=='full' and r['case']=='D_n2_mixed_scenario3' and r['compact_scip_A_seconds'] is not None:
                document+=[f"同一起点的 2 片混合实例均达到 324 s。原模型配完整学习选割、缩减模型配相同选割、缩减模型配 CP-SAT 的工期搜索分别用 {num(r['original_A_seconds'])}、{num(r['compact_scip_A_seconds'])}、{num(r['projected_A_seconds'])} s。三份离散排程在第二阶段分别取得 {num(r['original_fB'])}、{num(r['compact_scip_fB'])}、{num(r['projected_fB'])}。工期搜索最快的一组留下了较高的工艺目标。",'']
    extra=OUT/'spbs_policy_control'/'comparison.json'
    if extra.exists():
        ext=read(extra)
        if not ext['valid'] or len(ext['pairs'])!=len(TUNING):raise ValueError('Invalid same-policy initialization controls')
        document+=['### 保持同一学习选割策略时的初始化消融','',
                  '两个实例另补四个阶段，与主队列的启用 SPBS 结果配对。每例两臂使用同一可行起点、同一冻结选割网络与相同的双 0.01% 阈值。初始化开关控制从该可行起点开始的本轮 SPBS 改善。[逐例证据](spbs_policy_control/comparison.json)','']
        entries=[]
        for r in ext['pairs']:
            for prefix,label in [('with_spbs','启用'),('without_spbs','省略')]:
                entries.append([case_name(r['case']),label,*[num(r[f'{prefix}_{name}']) for name in ('cmax','fB','A_s','wall_s','calls')]])
        document+=table(['实例','SPBS','工期','固定结构工艺目标','第一阶段求解 s','实耗 s','学习选割调用'],entries)
    pre=[]
    for c in (*TUNING,'D_n4_mixed_H10','D_n16_4x1','E_n16_2x2'):
        e=all_e.get(c+'__initialization_reference')
        if e:pre.append([case_name(c),num(e['initial']['cmax']),num(e['metrics']['cmax']),num(e['wall_s'])])
    document+=table(['初始化单独复跑','输入工期','60 s SPBS 后工期','本轮实耗 s'],pre)
    document+=['## 固定预算对比、消融及权重扰动','',
               '仅用符合预算的配对计算均值。工期优先算法用 270 s 搜工期、30 s 优化工艺目标。归一化联合目标各用 300 s，节拍权重各用同种子、同一工期排程下的 60 s。','']
    pairs=[]
    for c in ('D_n4_mixed_H10','D_n16_4x1','E_n16_2x2'):
        for rho in (.01,.1,1.):
            for seed in SEEDS:
                one=f'{c}__budget_A_s{seed}'
                two=f'{c}__budget_B_s{seed}'
                joint=f'{c}__joint_rho{rho:g}_s{seed}'
                if not all(k in all_e for k in (one,two,joint)):continue
                a,b,j=(all_e[k] for k in (one,two,joint))
                if a['input_sha256']!=j['input_sha256'] or a['assignment_sha256']!=b['input_sha256']:raise ValueError('Unpaired objectives')
                pairs.append(dict(case=c,seed=seed,rho=rho,eligible=b['budget_eligible'] and j['budget_eligible'],
                            two_cmax=b['metrics']['cmax'],two_secondary=b['metrics']['secondary'],joint_cmax=j['metrics']['cmax'],
                            joint_secondary=j['metrics']['secondary'],two=two,joint=joint))
    output_csv('objective_pairs.csv',pairs)
    grouped=defaultdict(list)
    for p in pairs:grouped[p['case'],p['rho']].append(p)
    js=[]
    for (c,r),ps in grouped.items():
        good=[p for p in ps if p['eligible']]
        js.append([case_name(c),r,f'{len(good)}/{len(ps)}',*[num(mean(p[k] for p in good)) if good else '—' for k in ('two_cmax','two_secondary','joint_cmax','joint_secondary')]])
    document+=table(['实例','联合权重','合预算 / 完成配对','两阶段工期','两阶段工艺目标','联合工期','联合工艺目标'],js)
    stage=[]; structure=[]; rhythms=[]; method=[]; paired=[]
    for key,e in all_e.items():
        t=tasks[key]; c=t['case']
        if t['kind']=='secondary' and 'refinement-ablation' in t['tables']:
            stage.append(dict(case=c,seed=t['seed'],eligible=e['budget_eligible'],cmax=e['metrics']['cmax'],
                              wait_before=e['initial']['wait_sum'],wait_after=e['metrics']['wait_sum']))
        if t['kind']=='secondary' and 'rhythm-weight' in t['tables']:
            rhythms.append(dict(case=c,weight=t['weight'],seed=t['seed'],eligible=e['budget_eligible'],input=e['input_sha256'],input_cap=e['initial']['cmax'],
                                **e['metrics'],optimized_value=e['record']['upper']))
        if '__structure_' in key and 'prefix' not in key:
            typ=key.split('__structure_')[1].rsplit('_s',1)[0]
            structure.append(dict(case=c,method=typ,seed=t['seed'],eligible=e['budget_eligible'],**e['metrics']))
        if t['kind'] in ('scip','cp') and any(s in t['tables'] for s in ('journal-transfer','journal-algorithm')):
            typ=key.split('__')[1]
            method.append(dict(case=c,table=t['tables'][0],prep='plain' if '_plain_' in typ else 'spbs',arm=t.get('method','cp'),
                               seed=t['seed'],train=t.get('train'),eligible=e['budget_eligible'],**e['metrics']))
            if t['kind']=='scip':
                reference=historic_cut(key)
                typ='plain' if '_plain_' in key else 'spbs'
                cp=all_e.get(f'{c}__algorithm_{typ}_s{t["seed"]}')
                if cp is not None and cp['input_sha256']!=e['input_sha256']:raise ValueError('Cut/CP pairing mismatch')
                diff=None
                if reference:
                    src=SPEC['inputs'].get(t['start'])
                    own=src['assignment'] if src else rel(OUT/'runs'/t['start']/'assignment.json.gz')
                    diff=(0. if e['input_sha256']==reference['reference_input'] else
                          assignment_difference(own,reference['reference_input_file']))
                paired.append(dict(case=c,cell=key,method=t['method'],seed=t['seed'],training_seed=t['train'],
                             cp_cmax=None if cp is None else cp['metrics']['cmax'],bounded_scip_cmax=e['metrics']['cmax'],
                             cp_seconds=None if cp is None else cp['record']['seconds'],bounded_scip_seconds=e['record']['seconds'],
                             cp_budget_ok=None if cp is None else cp['budget_eligible'],bounded_scip_budget_ok=e['budget_eligible'],
                             input_matches_archive=e['input_sha256']==reference.get('reference_input'),max_input_difference=diff,
                             input_values_match_archive=None if diff is None else diff<=1e-6,**reference))
    def means(data,keys,columns,all_runs=False):
        grouped=defaultdict(list)
        for x in data:grouped[tuple(x[k] for k in keys)].append(x)
        result=[]
        for grouping,rows in grouped.items():
            group=list(grouping)
            if group[0] in SPEC['cases']:group[0]=case_name(group[0])
            good=[x for x in rows if x['eligible']]
            row=group+[f'{len(good)}/{len(rows)}']+[num(mean(x[col] for x in good)) if good else '—' for col in columns]
            if all_runs:row.extend(num(mean(x[col] for x in rows)) for col in columns)
            result.append(row)
        return result
    document+=['### 第二阶段消融','']+table(['实例','合预算 / 完成','工期','阶段一末总等待','阶段二末总等待'],means(stage,['case'],['cmax','wait_before','wait_after']))
    document+=['### 16 片节拍权重','']+table(['实例','权重','合预算 / 完成','工期','路线总等待','最大等待','节拍偏差','有效节拍项数'],means(rhythms,['case','weight'],['cmax','wait_sum','wait_max','rhythm','rhythm_centers']))
    for seed in SEEDS:
        r=[v for v in rhythms if v['seed']==seed]
        if len({(v['input'],v['input_cap']) for v in r})>1:raise ValueError('Unpaired rhythm weights')
    if len(rhythms)==12:
        document+=['对每个种子，四档权重共享同一份第一阶段排程和工期上界。第二阶段允许产品提前返回，因此表中的实际工期可以低于共同上界。[节拍逐种子结果](rhythm_weights.csv)','']
    document+=['### 固定与开放离散结构','']+table(['实例','结构策略','合预算 / 完成','工期'],means(structure,['case','method'],['cmax']))
    output_csv('refinement_pairs.csv',stage)
    output_csv('rhythm_weights.csv',rhythms)
    output_csv('structure_cells.csv',structure)
    output_csv('component_pairs_with_original.csv',paired)
    strategy=[]
    for row in method:
        t1=row['train'] in (None,1)
        if row['table']=='journal-transfer':
            strategy.append(dict(row,population='供片场景，文稿种子'))
        else:
            if t1:strategy.append(dict(row,population='原表，训练种子1'))
            if 'mixed' in row['case']:strategy.append(dict(row,population='混合配方扩展，训练种子1至3'))
    output_csv('algorithm_groups.csv', [dict(zip(['case','population','initialization','method','eligible_completed','budget_eligible_mean_cmax','all_completed_mean_cmax'],row))
               for row in means(strategy,['case','population','prep','arm'],['cmax'],all_runs=True)])
    if strategy:
        document+=['### 固定预算下的算法与供片场景','',
                   '表格给出合预算的平均工期（s），方括号内为合预算组数 / 已完成组数。默认 SCIP 和 CP-SAT 各取三个求解种子。供片场景的学习方法取三个训练种子与三个求解种子的九种组合。混合实例的三训练种子扩展，以及全部已完成种子的均值，另列在明细中。[算法分组](algorithm_groups.csv)','']
        groups=defaultdict(list)
        for r in strategy:groups[r['population'],r['case'],r['prep'],r['arm']].append(r)
        def group_value(group,case,prep,arm):
            sample=groups[group,case,prep,arm]
            if not sample:return '待完成'
            good=[r['cmax'] for r in sample if r['eligible']]
            return f"{num(mean(good)) if good else '—'} [{len(good)}/{len(sample)}]"
        basic=['D_n2_4x1_crossLP','D_n2_4x1_sameLP','D_n2_mixed','D_n4_mixed_H10']
        if any(r['table']=='journal-algorithm' for r in strategy):
            document+=table(['原表训练种子 1','初始化','CP-SAT','SCIP 默认','HEM','完整学习选割'],[
                [case_name(c),'直接' if prep=='plain' else 'SPBS',
                 *[group_value('原表，训练种子1',c,prep,arm) for arm in ('cp','default','hem_spbs','full')]]
                for c in basic for prep in ('plain','spbs')])
        transfer_cases=[c for c in SPEC['cases'] if any('journal-transfer' in t['tables'] and t['case']==c for t in tasks.values())]
        if any(r['table']=='journal-transfer' for r in strategy):
            options=[(p,a) for p in ('plain','spbs') for a in (('cp','default','hem_spbs','full') if p=='plain' else ('cp','default',*POLICIES))]
            document+=table(['方法','初始化',*[case_name(c).split(' H')[0].removeprefix('2片 ') for c in transfer_cases]],[
               [METHOD_NAMES.get(arm,'CP-SAT'),'直接' if prep=='plain' else 'SPBS',
                *[group_value('供片场景，文稿种子',c,prep,arm) for c in transfer_cases]] for prep,arm in options])
    if paired:document+=['本轮 CP-SAT 与缩减后 SCIP 逐种子共享同一份输入。历史对照另核对进入工期搜索的赋值文件，并记录所有变量的最大差值，数值匹配容差取 0.000001。各列保留实际求解时间和预算标记。[逐种子对照](component_pairs_with_original.csv)','']
    document+=[
               '## 75 片混跑与排程图','',
               f"37 片 4×1 与 38 片 2×2。从已核验的 {scale['start']} s 出发，本轮达到 {scale['upper']} s，全局下界 {scale['lower']} s，间隙 {scale['gap']*100:.4f}%。两腔在末片返回前合计空闲 {scale['idle']['idle']} s，设备占用到 {scale['idle']['equipment_end']} s。"
               +('已达到切换门槛。' if scale['gate'] else '0.001% 全局切换门槛尚未达到，本轮未启动空闲目标求解。'),
               f"该排程通过 {scale['original_rows']:,} 条原模型约束和 {scale['replay']['checks']:,} 项物理事件检查。本次进程峰值 {scale['resources']['peak_rss_mib']} MiB。[75 片甘特图](figures/n75/gantt.pdf)",'']
    document+=[f"可行工期与全局下界相差 {num(scale['upper']-scale['lower'])} s。下界来自保留双腔、清洁和共享 VTR 冲突的松弛模型。两腔实测空闲占末片回片前双腔总可用时间的 {num(100*scale['idle']['idle']/(2*scale['upper']))}%。",'']
    for size,c,tag in [('n2','D_n2_4x1_sameLP','structure_joint_s1'),('n16','D_n16_4x1','budget_A_s1')]:
        key=c+'__'+tag
        if key in all_e:document+=[f"{case_name(c)}的末片返回工期为 {num(all_e[key]['metrics']['cmax'])} s。[排程图](figures/{size}/gantt.pdf)",'']
    document+=['## 进度、续跑和数据','',
              '在仓库根目录的 PowerShell 中运行下面的命令，会打开当前终端的实时进度并接续未完成单元。完成的单元按证据文件跳过。被中断的固定预算单元从共同起点重新计时，间隙单元可复用已保存的有效下界，75 片另从最后一个完整窗口继续。[总进度](progress.json) · [逐单元数据](all_cells.csv)','',
              '```powershell',r'& .\JMS-version\experiments\manuscript_projection_20261120\launch.ps1 -Task campaign',
              r'& .\JMS-version\experiments\manuscript_projection_20261120\launch.ps1 -Task scale',
              r"& 'G:\conda\python.exe' -B -X utf8 .\JMS-version\experiments\manuscript_projection_20261120\spbs_control.py",'```','']
    document+=['随求解刷新数据表时可在另一终端运行以下命令。主队列和补充对照都结束后，可用同一脚本的 `--verify` 核对整轮数据。','',
              '```powershell',r"& 'G:\conda\python.exe' -B -X utf8 .\JMS-version\experiments\manuscript_projection_20261120\report.py --follow",'```','']
    if (OUT/'verification.json').is_file():
        document+=['已核对全部实验覆盖、逐阶段目标与数据哈希，并独立重放最终排程。[整轮核验记录](verification.json)','']
    output_csv('all_cells.csv',fixed_table(all_e))
    save(OUT/'table_status.json',dict(expected=len(tasks),complete=len(all_e),by_table={
        k:dict(expected=sum(k in t['tables'] for t in tasks.values()),complete=sum(k in tasks[s]['tables'] for s in all_e)) for k in SPEC['tables']},
        by_size={n:dict(expected=sum(t['n']==n for t in tasks.values()),complete=sum(tasks[s]['n']==n for s in all_e)) for n in (2,4,16)},
        same_policy_spbs_extra_stages=read(extra)['tasks'] if extra.exists() else 0,
        two_gap_choice=chosen,scale75_complete=True,workers_failed=list(progress['failed']),missing=sorted(set(tasks)-all_e.keys())))
    f=OUT/'REPORT_CN.md'
    f.with_suffix('.tmp').write_text('\n'.join(document),encoding='utf-8')
    f.with_suffix('.tmp').replace(f)
    print('Generated report for',len(all_e),'of',len(tasks),'small/medium tasks and the D75 run')


if __name__=='__main__':
    arg=argparse.ArgumentParser()
    modes=arg.add_mutually_exclusive_group()
    modes.add_argument('--replay',choices=('D','E'))
    modes.add_argument('--follow',action='store_true')
    modes.add_argument('--verify',action='store_true')
    arg.add_argument('--replay-only',action='store_true',help=argparse.SUPPRESS)
    args=arg.parse_args()
    if args.replay:
        check_backend(args.replay)
        if (args.replay=='E' and not args.replay_only and (OUT/'completion.json').is_file()
            and (OUT/'replay_D.json').is_file() and (OUT/'spbs_policy_control/comparison.json').is_file()):
            status=read(OUT/'completion.json')
            spec=read(OUT/'protocol.json')
            done_d=read(OUT/'replay_D.json')['cells']
            if (status['completed']==len(spec['tasks']) and not status['failed'] and not status['dependent_pending']
                and done_d==sum(t['backend']=='D' for t in spec['tasks'].values())):
                verify_complete(replay_again=False)
    elif args.verify: verify_complete()
    elif args.follow:
        previous=-1
        while True:
            p=read(OUT/'progress.json')
            if p['completed']!=previous or (OUT/'completion.json').is_file():
                build()
                previous=p['completed']
            if (OUT/'completion.json').is_file():
                final=read(OUT/'completion.json')
                if final['completed']==final['expected'] and not final['failed'] and not final['dependent_pending']:
                    for family in ('D','E'):
                        subprocess.run([sys.executable,'-B','-X','utf8',str(Path(__file__).resolve()),'--replay',family],check=True)
                    break
                sys.exit('Unfinished runs remain; the verified partial report is available')
            time.sleep(60)
    else: build()
