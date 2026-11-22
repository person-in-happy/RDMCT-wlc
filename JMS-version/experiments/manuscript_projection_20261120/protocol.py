"""Cell definitions from the dated Chinese manuscript. Time budgets are solver seconds."""
from collections import Counter
from itertools import product
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
ROOT=JMS.parent
sys.path.insert(0,str(HERE.parent/'manuscript_certified_gaps_20261119'))
from design import LEVELS, TUNING, read, rel, save, sha

RESULTS=JMS/'results'
OUT=RESULTS/'manuscript_projection_20261120_r1'
BASE=RESULTS/'manuscript_certified_gaps_20261119_r3'
TABLES=('certified-grid','certified-spbs','certified-cuts','joint-two-stage','refinement-ablation',
        'rhythm-weight','structure-ablation','journal-structure','journal-algorithm','journal-transfer')
POLICIES=('hem_spbs','feature_only','no_rerank','greedy','full')
PYTHON_CP=Path(sys.base_prefix)/'python.exe'
PYTHON_SCIP=Path('G:/conda/envs/a3cenv/python.exe')
SEEDS=(1,2,3)


def matrix():
    instances=read(RESULTS/'manuscript_cases_A0p001pct_B0p001pct_20261119/campaign.json')['cases']
    cases={c['id']:c for c in instances if c['n'] in (2,4,16)}
    past=read(BASE/'protocol.json')
    objects={}
    tasks={}
    def source(key,schedule,assignment):
        schedule,assignment=Path(schedule),Path(assignment)
        if not schedule.is_absolute(): schedule=ROOT/schedule
        if not assignment.is_absolute(): assignment=ROOT/assignment
        objects[key]=dict(schedule=rel(schedule),assignment=rel(assignment),
                          schedule_sha256=sha(schedule),assignment_sha256=sha(assignment))
        return key
    def job(case,kind,tag,start,tables,**settings):
        key=f'{case}__{tag}'
        if key in tasks: raise ValueError(key)
        deps=[start] if start in tasks else []
        tasks[key]=dict(id=key,case=case,kind=kind,start=start,deps=deps,tables=list(tables),
                        backend=cases[case]['backend'],n=cases[case]['n'],**settings)
        return key
    for case,c in cases.items():
        k=source(case+'/raw',c['source'],c['assignment'])
        assert objects[k]['assignment_sha256']==c['assignment_sha256'] and objects[k]['schedule_sha256']==c['source_sha256']
    for case in (*TUNING,'D_n4_mixed_H10','D_n16_4x1','E_n16_2x2'):
        item=past['cases'][case]
        raw=ROOT/item['raw']
        schedule=raw.parent/('final.json' if raw.name=='final_assignment.json.gz' else 'result.json')
        source(case+'/cert_raw',schedule,raw)
        prep=BASE/'runs'/case/'prep'
        seed=read(prep/'evidence.json')
        k=source(case+'/cert_prep',prep/'schedule.json',prep/'assignment.json.gz')
        assert seed['valid'] and seed['assignment_sha256']==objects[k]['assignment_sha256'] and seed['schedule_sha256']==objects[k]['schedule_sha256']
        objects[k]['prep_seconds']=seed['prep_seconds']
        job(case,'prep','initialization_reference',case+'/cert_raw',['certified-spbs'],seed=1,seconds=60)
    for case in TUNING:
        warm=case+'/cert_prep'
        for a in LEVELS:
            primary=job(case,'cp','grid_A_'+a,warm,['certified-grid'],seed=1,seconds=None,gap=LEVELS[a],bounds=True,structure='free')
            for b in LEVELS:
                job(case,'secondary','grid_B_'+a+'_'+b,primary,['certified-grid'],seed=1,seconds=None,gap=LEVELS[b],weight=25)
        # SPBS and component controls follow the parameter choice produced by this grid.
        # All nine stages are already available for the warmed full method.
        for start,method in ((case+'/cert_raw','no_spbs'),(warm,'unreduced')):
            job(case,'selected','selected_'+method,start,['certified-spbs' if method=='no_spbs' else 'certified-cuts'],
                seed=1,seconds=None,bounds=method!='unreduced',structure='free',engine='cp',method=method)
        for method in POLICIES:
            job(case,'selected','selected_cut_'+method,warm,['certified-cuts'],seed=1,train=1,seconds=None,
                bounds=True,structure='free',engine='scip',method=method)
    objectives=('D_n4_mixed_H10','D_n16_4x1','E_n16_2x2')
    for case,c in cases.items():
        raw=case+'/raw'
        refs=[s.removeprefix('tab:').removesuffix('-cn') for s in c['manuscript'] if s.startswith('tab:')]
        for seed in SEEDS:
            if 'refinement-ablation' in refs or case in objectives:
                table='joint-two-stage' if case in objectives else 'refinement-ablation'
                first=job(case,'cp',f'budget_A_s{seed}',raw,[table],seed=seed,seconds=270,gap=None,bounds=True,structure='free')
                job(case,'secondary',f'budget_B_s{seed}',first,[table],seed=seed,seconds=30,gap=None,weight=25)
                if case in objectives:
                    for rho in (.01,.1,1.):
                        job(case,'weighted',f'joint_rho{rho:g}_s{seed}',raw,['joint-two-stage'],seed=seed,seconds=300,rho=rho)
                if 'rhythm-weight' in refs:
                    for w in (0,5,25,100):
                        job(case,'secondary',f'rhythm_w{w}_s{seed}',first,['rhythm-weight'],seed=seed,seconds=60,gap=None,weight=w)
            struct=next((t for t in ('structure-ablation','journal-structure') if t in refs),None)
            if struct:
                for tag,limit,fixed in [('joint',300,'free'),('fixed',300,'fixed'),('prefix',60,'fixed')]:
                    j=job(case,'cp',f'structure_{tag}_s{seed}',raw,[struct],seed=seed,seconds=limit,gap=None,bounds=True,structure=fixed)
                    if tag=='prefix':
                        job(case,'cp',f'structure_fix_then_free_s{seed}',j,[struct],seed=seed,seconds=240,gap=None,bounds=True,structure='free')
            transfer='journal-transfer' in refs
            if 'journal-algorithm' in refs or transfer:
                table='journal-transfer' if transfer else 'journal-algorithm'
                if transfer:
                    key=case.removeprefix('D_')
                    path=RESULTS/'journal_d_transfer_20261109_r1/runs'/f'{key}__s{seed}__t1__shared_spbs'
                    pre=source(case+f'/fixed_prep_s{seed}',path/'result.json',path/'variables.json')
                    ev=read(path/'evidence.json')
                    assert ev['valid'] and ev['variables_sha256']==objects[pre]['assignment_sha256']
                    objects[pre]['prep_seconds']=ev['initialization_wall_seconds']
                    cell=ev['cell']
                    registered=source(case+'/transfer_raw',cell['source'],cell['values'])
                    raw_input=registered
                else:
                    raw_input=raw
                    pre=job(case,'prep',f'fixed_prep_s{seed}',raw,[table],seed=seed,seconds=60)
                for suffix,inp,sec in [('plain',raw_input,300),('spbs',pre,240)]:
                    job(case,'cp',f'algorithm_{suffix}_s{seed}',inp,[table],seed=seed,seconds=sec,gap=None,bounds=True,structure='free')
                    # The cut policies run in their SCIP backend with common safe capacity bounds.
                    methods=('default','hem_spbs','full') if not transfer or suffix=='plain' else ('default',*POLICIES)
                    for method in methods:
                        trains=(1,) if method=='default' or (not transfer and 'mixed' not in case) else SEEDS
                        for train in trains:
                            job(case,'scip',f'cut_{suffix}_{method}_s{seed}_t{train}',inp,[table],seed=seed,
                                train=train,seconds=sec,gap=None,bounds=True,method=method,structure='free')
    # Figure 2 and figure 16 have their own H=3, D=8 sources. The figure protocol is feasibility.
    for case,linked in [('D_n2_4x1_sameLP','structure_joint_s1'),('D_n16_4x1','budget_A_s1')]:
        tasks[f'{case}__{linked}']['figure']=True
    grid_b=[k for k,v in tasks.items() if v['kind']=='secondary' and 'certified-grid' in v['tables']]
    for t in tasks.values():
        if t['kind']=='selected': t['deps']+=grid_b
    sources=[HERE/'protocol.py',HERE/'cell.py',HERE/'gantt.py',HERE/'campaign.py',
             HERE.parent/'sublevel_bounds_20261120/project.py',HERE.parent/'sublevel_bounds_20261120/bounds.py',
             HERE.parent/'component_gap_restore_20261119/component.py']
    for name in ('model4_pjob_nonprocessing_20261103','model4_pjob_nondecreasing_20261102'):
        sources.extend((JMS/name).glob('*.py'))
    return dict(cases=cases,inputs=objects,tasks=tasks,tables=list(TABLES),thresholds=LEVELS,
                manuscript=rel(JMS/'JMS_Review_CN.tex'),manuscript_sha256=sha(JMS/'JMS_Review_CN.tex'),
                assets={rel(p):sha(p) for p in sources},seeds=list(SEEDS),cpu_threads=1,gpu=False,
                concurrent_processes=8,max_16_wafer_processes=2,groups=Counter(t['kind'] for t in tasks.values()),
                fixed_budget_tolerance_s=1.,scale75='mixed-only demonstration, independent protocol and checkpoint')
