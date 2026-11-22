"""Matched objective, cut-policy and initialization controls; run from a visible console."""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'manuscript_projection_20261120'))
import cell
from protocol import JMS, ROOT, read, save, sha

OUT = JMS / 'results/matched_controls_20261122_r2'
CASES = {case['id']: case for case in read(JMS / 'results/manuscript_cases_A0p001pct_B0p001pct_20261119/campaign.json')['cases']}
SMALL = ('E_n4_H10_mixed_dual', 'E_n8_H10_mixed_dual')
LARGE = ('D_n16_4x1', 'E_n16_2x2')
ARMS = ('A', 'B', 'AB')
METHODS = ('full', 'plain_full', 'default', 'hem_spbs', 'no_rerank', 'greedy', 'feature_only', 'cp')


def objective_stage(cfg, start, vals, arm, seconds, task, folder):
    import model
    from scip_imports import scip
    instance = model.Integrated(cfg)
    solver = instance.model
    cell.scip_settings(solver, dict(task, seconds=seconds), folder)
    variables = {var.name: var for var in solver.getVars(transformed=False)}
    vals = dict(vals)
    vals[instance.cmax.name] = start['cmax']
    vals[instance.max_wait.name] = start['wait_max']
    extra = {}
    pitches = []
    for chamber in cfg.chambers:
        for slot in range(2, instance.Q):
            previous = instance.keep[chamber, slot - 1]
            current = instance.keep[chamber, slot]
            rhythm = variables[f'rhythm_{chamber}_{slot}']
            active = vals.get(previous.name, 0.) > .5 and vals.get(current.name, 0.) > .5
            times = [vals.get(instance.cy.start[chamber, index].name, 0.) for index in (slot, slot-1, slot-2)]
            vals[rhythm.name] = max(0., abs(times[0]-2*times[1]+times[2]) - (0 if active else instance.M))
            pitch = solver.addVar(lb=0, ub=cfg.horizon, name=f'physical_pitch_{chamber}_{slot}')
            solver.addCons(pitch >= rhythm - cfg.horizon * (2 - previous - current))
            extra[pitch.name] = max(0., vals.get(rhythm.name, 0.) - cfg.horizon * (2 - vals.get(previous.name, 0.) - vals.get(current.name, 0.)))
            pitches.append(pitch)
    score = scip.quicksum(instance.waits) + 10 * instance.max_wait + 25 * scip.quicksum(pitches)
    solver.setObjective(score if arm == 'B' else instance.cmax, 'minimize')
    warm = cell.attach(instance, vals | extra)
    if abs(solver.getSolObjVal(warm) - start['secondary' if arm == 'B' else 'cmax']) > cell.EPS:
        raise ValueError('Initial physical objective mismatch')
    solver.addSol(warm)
    solver.optimize()
    incumbent = solver.getBestSol()
    result = {name: solver.getSolVal(incumbent, var) for name, var in variables.items()}
    record = dict(status=str(solver.getStatus()), seconds=solver.getSolvingTime(), budget=seconds,
                  nodes=solver.getNNodes(), lower=solver.getDualbound(), upper=solver.getPrimalbound())
    solver.freeProb()
    checked = cell.lift(cfg, result, None)
    if not checked or abs(checked[2]['secondary' if arm == 'B' else 'cmax'] - record['upper']) > cell.EPS:
        raise ValueError('Final objective disagrees with original model / replay')
    return checked, record


def worker(case_id, seed, arm):
    case = CASES[case_id]
    sys.path.insert(0, str(cell.BACKENDS[case['backend']]))
    import model
    cfg = model.Config(**case['config'])
    folder = OUT / f'{case_id}__s{seed}__{arm}'
    folder.mkdir(parents=True, exist_ok=True)
    task = dict(n=case['n'], seed=seed, train=1, bounds=True, structure='free')
    schedule, assignment = ROOT / case['source'], ROOT / case['assignment']
    if (sha(schedule), sha(assignment)) != (case['source_sha256'], case['assignment_sha256']):
        raise ValueError('Frozen source changed')
    data, vals = read(schedule), cell.values(assignment)
    if case_id in LARGE:
        spec = read(cell.OUT/'protocol.json')
        source = spec['inputs'][case_id+'/cert_raw']
        schedule, assignment = ROOT/source['schedule'], ROOT/source['assignment']
        data, vals, _ = cell.get_source(spec, dict(start=case_id+'/cert_raw'))
    checked = cell.certify_start(cfg, data, vals)
    original = checked[2]
    stages = []
    def store(name, result, record, budget):
        target = folder / name
        save(target / 'schedule.json', result[0]); save(target / 'assignment.json.gz', result[1])
        stages.append(dict(record=record, budget=budget, metrics=result[2], replay=result[3], rows=result[4],
                           schedule_sha256=sha(target/'schedule.json'), assignment_sha256=sha(target/'assignment.json.gz')))
        save(target / 'stage.json', stages[-1])
    if arm in ARMS:
        budget = 270 if arm == 'AB' else 300
        checked, record = objective_stage(cfg, original, vals, arm, budget, task, folder)
        store('free', checked, record, budget)
    else:
        budget = 270
        if arm != 'plain_full':
            prepared, warm, evidence = cell.get_source(spec, dict(start=case_id+'__initialization_reference'))
            if evidence['input_sha256'] != sha(assignment): raise ValueError('Different raw initialization')
            checked = cell.certify_start(cfg, prepared, warm)
            store('spbs', checked, evidence['record'], 60)
            budget -= 60
        first = folder / 'primary'; first.mkdir(exist_ok=True)
        checked, record = cell.primary(dict(task, kind='cp' if arm == 'cp' else 'scip', method='full' if arm == 'plain_full' else arm,
                                            seconds=budget), cfg, checked[0], checked[1]['nonzero'], first, sha(assignment))
        store('primary', checked, record, budget)
    if arm == 'AB' or arm not in ARMS:
        second = folder / 'retime'; second.mkdir(exist_ok=True)
        checked, record = cell.other(dict(task, kind='secondary', seconds=30), cfg, checked[0], checked[1]['nonzero'], second)
        store('retime', checked, record, 30)
    eligible = all(stage['record']['seconds'] <= stage['budget'] + 1 and stage['record']['status'].lower() not in
                   ('memlimit', 'memorylimit', 'userinterrupt', 'unknown') for stage in stages)
    save(folder / 'result.json', dict(case=case_id, seed=seed, arm=arm, eligible=eligible, initial=original,
                                      input_sha256=sha(assignment), metrics=checked[2], stages=stages))


def campaign():
    jobs = [(case, seed, arm) for seed in (1, 2, 3) for case in SMALL + LARGE for arm in (ARMS if case in SMALL else METHODS)]
    OUT.mkdir(exist_ok=True)
    save(OUT / 'design.json', dict(jobs=jobs, solver_threads=1, training_seed=1, max_parallel=2, seconds=300,
                                   source_sha256=sha(__file__), tolerance_per_stage_seconds=1))
    def launch(job):
        case, seed, arm = job
        folder = OUT / f'{case}__s{seed}__{arm}'; folder.mkdir(exist_ok=True)
        if (folder / 'result.json').is_file(): return True
        executable = 'G:/conda/python.exe' if arm == 'cp' else 'G:/conda/envs/a3cenv/python.exe'
        with (folder / 'worker.log').open('w', encoding='utf-8') as log:
            return subprocess.run([executable, '-B', '-X', 'utf8', __file__, case, str(seed), arm], stdout=log, stderr=subprocess.STDOUT).returncode == 0
    with ThreadPoolExecutor(2) as pool:
        pending = [pool.submit(launch, job) for job in jobs]
        started = time.monotonic()
        while True:
            finished = [future for future in pending if future.done()]
            failed = sum(not future.result() for future in finished)
            left = len(jobs) - len(finished)
            eta = round(left * ((time.monotonic()-started)/len(finished) if finished else 150)/60)
            print(f'Completed {len(finished)-failed}/{len(jobs)} | failed {failed} | remaining {left} | ETA ~{eta} min', flush=True)
            save(OUT / 'progress.json', dict(completed=len(finished)-failed, failed=failed, remaining=left, eta_minutes=eta))
            if not left: return int(bool(failed))
            time.sleep(10)


if __name__ == '__main__':
    if len(sys.argv) == 4: worker(sys.argv[1], int(sys.argv[2]), sys.argv[3])
    else: sys.exit(campaign())
