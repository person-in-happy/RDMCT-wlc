"""Pass certified first-stage assignments to the unchanged physical B worker in an isolated corpus."""
import shutil
import sys
from pathlib import Path
from compare import ARCHIVE, CASES, GAP, HERE, JMS
from design import read, rel, save, sha

sys.path.insert(0,str(HERE.parent/'manuscript_fixed_rhythm_20261119'))
import secondary

OUT=JMS/'results/sublevel_handoff_20261120_r1'


def run(case):
    parent=JMS/'results/sublevel_projection_20261120_r1'/case/'complete'
    a=read(parent/'result.json')
    if not (a['gate'] and a['mode']=='complete' and a['new_witness'] and a['replay']['valid']
            and sha(parent/'assignment.json.gz')==a['assignment_sha256'] and sha(parent/'schedule.json')==a['schedule_sha256']
            and a['upper']>=a['lower']>0 and (a['upper']-a['lower'])/a['lower']<=GAP):
        raise ValueError('Unverified A certificate')
    stage=dict(phase='primary',status='optimal' if a['upper']==a['lower'] else 'gaplimit',
               primal_bound=a['upper'],dual_bound=a['lower'],relative_gap=a['gap'],
               bound_scope='global_product_Cmax',seconds=a['solver_s'],limit=a['limit_s'],
               backend='integer outer relaxation; original-model replay')
    gate=secondary.gap_certificate(stage,GAP)
    if not gate['accepted']:raise ValueError(gate)
    aout=OUT/'runs'/case/'full'/'A_0p01pct'
    aout.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(parent/'assignment.json.gz',aout/'assignment.json.gz')
    save(aout/'evidence.json',dict(valid=True,phase='A',scope='global_product_Cmax',case=case,arm='full',
        source=rel(parent),source_sha256=sha(parent/'result.json'),record=stage,gate=gate,threshold=GAP,
        assignment_sha256=a['assignment_sha256'],metrics={'cmax':a['upper']}))
    dest=aout.parent/'B_0p01pct_0p01pct'
    attempt=dest/'attempts'/'1'
    attempt.mkdir(parents=True)
    secondary.worker(case,'full','0p01pct','0p01pct',dest,attempt)
    b=read(dest/'evidence.json')
    print(case,'physical B',b['metrics']['secondary'],'gap',b['gate']['recomputed_gap'],'verified wall',b['elapsed'],flush=True)


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ARCHIVE/'protocol.json',OUT/'protocol.json')
    secondary.PRIMARY=OUT
    for i,case in enumerate(CASES):
        print(f'Completed {i}/2, failed 0 | {case} | gap-terminated B, ETA pending',flush=True)
        run(case)
    print('Completed 2/2',flush=True)
