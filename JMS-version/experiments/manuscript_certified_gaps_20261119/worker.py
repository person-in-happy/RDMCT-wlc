"""Solve one certified stage. Separate processes keep the two SCIP models out of RAM together."""
import importlib
import math
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from design import (EPS, HERE, JMS, LEVELS, METHODS, ROOT, SEED, TRAINING_SEED,
                    read, rel, save, sha, sparse, witness)

sys.path.insert(0, str(HERE.parent / 'gap_both_stages_20261118'))
from gap_two_stage import f, finite, gap_certificate, stage_record


def install_cpu(m, method):
    # The training launcher is CUDA-only. Load the same inference modules and weights on CPU.
    import torch
    import numpy as np
    from joint_algorithms import policy_record
    sys.path.insert(0, str(ROOT / 'cie/code'))
    import run_cie_benchmarks as cie
    torch.set_num_threads(1)
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    record = policy_record(method, TRAINING_SEED)
    cfg = read(record['config'])
    checkpoint = torch.load(record['checkpoint'], map_location='cpu', weights_only=False)
    dim = cfg['net_share']['embedding_dim']
    cie.validate_checkpoint_feature_schema(checkpoint, dim, record['checkpoint'])
    cie.validate_checkpoint_postprocessor_schema(checkpoint, dim, record['checkpoint'], 'role_submodular_v1')
    net = cfg['net_share']
    args = dict(embedding_dim=dim, hidden_dim=net['hidden_dim'], tanh_exploration=net['tanh_exploration'],
                use_tanh=net['use_tanh'], use_cuda=False)
    pointer = cie.PointerNetworkEndToken(**args, n_glimpses=cfg['policy']['n_glimpses'], beam_size=cfg['policy']['beam_size'])
    high = cie.CutsPercentPolicy(**args, n_process_block_iters=cfg['value']['n_process_block_iters'])
    pointer.load_state_dict(checkpoint['pointer_net'])
    high.load_state_dict(checkpoint['cutsel_percent_net'])
    pointer.eval()
    high.eval()
    norm = None
    if 'mean' in checkpoint:
        norm = cie.RunningMeanStd((dim,))
        norm.set_mean_std(checkpoint['mean'], checkpoint['std'])
    bundle = dict(policy=pointer, high_level=high, mean_std=norm, device='cpu')
    params = SimpleNamespace(sel_cuts_percent=.2, decode_type='beam_search', policy_type='with_token',
           cutsel_max_candidates=128, cutsel_max_selected_cuts=16, structure_pool_factor=2.,
           structure_anchor_ratio=.25, structure_quality_weight=.35, structure_policy_weight=.20,
           structure_coverage_weight=.25, structure_representation_weight=.20)
    agent = cie._build_agent(SimpleNamespace(m=m), bundle, params, method == 'proposed')
    m.includeCutsel(agent, 'manuscript_cutsel', 'frozen manuscript cut selector', 666666)
    return agent, record


def route_bound(x):
    """All products use the single AL. Keep only compulsory work before/after its last release."""
    cfg = x.cfg
    products = [j for j in x.jobs.values() if j['product'] is not None]
    # There are two candidate product routes per pair. Inventory constraints
    # activate exactly N of them. Every route that can carry a product uses AL.
    if len(products) < len(x.products) or any('al_put' not in j for j in products):
        raise ValueError('Serial AL bound requires every product to visit AL')
    exposure = min(cfg.full_time if w.mode == '4x1' else 2 * cfg.mix_time for w in x.products)
    before = cfg.atr_handling + cfg.atr_travel
    serial = len(x.products) * (2 * cfg.atr_handling + cfg.alignment)
    after = (2 * cfg.atr_travel + 3 * cfg.atr_handling + cfg.pump + cfg.vent
             + 4 * cfg.handling + 2 * cfg.vtr_travel + exposure)
    return before + serial + after


def solve(out, case, task, folder, attempt):
    import psutil
    sys.path.insert(0, str(f.BACKENDS[case['backend']]))
    sys.path.insert(1, str(ROOT))
    backend = importlib.import_module('model')
    from validate import validate
    from scip_imports import scip
    from joint_algorithms import improve_skeleton
    random.seed(SEED)
    started = time.monotonic()
    stage, arm, a, b = task
    method, use_spbs = METHODS[arm]
    threshold = LEVELS[a if stage == 'A' else b] if stage in ('A','B') else None
    progress = folder / 'progress.json'
    save(progress, dict(phase='build', attempt=attempt.name))
    x = backend.Integrated(backend.Config(**case['config']))
    m = x.model
    vs = m.getVars(transformed=False)
    m.setIntParam('parallel/maxnthreads', 1)
    m.setIntParam('lp/threads', 1)
    m.setIntParam('randomization/randomseedshift', SEED)
    m.setIntParam('timing/clocktype', 2)
    m.setRealParam('limits/memory', case['scip_memory_mib'])
    m.setLogfile(str(attempt / 'scip.log'))
    m.hideOutput()
    def as_sol(vals):
        s = m.createSol()
        for v in vs:
            m.setSolVal(s, v, vals[v.name])
        return s
    def decode(s):
        if not m.checkSol(s, printreason=True, completely=True, original=True):
            raise ValueError('Assignment rejected by original rows')
        data = x.result(solution=s)
        check = validate(data)
        if not check['valid']:
            raise ValueError(str(check['errors'][:5]))
        data.update(original_model_check=True, validation=check)
        return data, f.physical_metrics(data)
    def tighten(s, metrics):
        m.setSolVal(s, x.cmax, metrics['cmax'])
        m.setSolVal(s, x.max_wait, metrics['wait_max'])
        by_name = {v.name:v for v in vs}
        for c in x.cfg.chambers:
            for q in range(2, x.Q):
                active = m.getSolVal(s, x.keep[c,q]) > .5 and m.getSolVal(s, x.keep[c,q-1]) > .5
                delta = abs(m.getSolVal(s, x.cy.start[c,q] - 2*x.cy.start[c,q-1] + x.cy.start[c,q-2])) if active else 0.
                m.setSolVal(s, by_name[f'rhythm_{c}_{q}'], delta)
    dependency = None
    source = ROOT / case['raw']
    if stage == 'A' and use_spbs:
        dependency = out / 'runs' / case['id'] / 'prep'
    elif stage == 'B':
        dependency = folder.parent / ('A_' + a)
    if dependency:
        cert = read(dependency / 'evidence.json')
        source = dependency / 'assignment.json.gz'
        if not cert['valid'] or sha(source) != cert['assignment_sha256']:
            raise ValueError('Invalid stage dependency')
        if stage == 'B' and (cert['phase'] != 'A' or not cert['gate']['accepted'] or cert['threshold'] != LEVELS[a]):
            raise ValueError('Secondary requested before the full-domain gap gate')
    if stage == 'prep' and case.get('shared'):
        source = ROOT / case['shared']
        prior = read(ROOT / case['shared_evidence'])
        if not prior['valid'] or prior['variables_sha256'] != sha(source) or prior['cell']['seed'] != SEED:
            raise ValueError('Unmatched cached SPBS input')
    vals = witness(source, vs)
    warm = as_sol(vals)
    data, initial = decode(warm)
    tighten(warm, initial)
    vals = {v.name:m.getSolVal(warm,v) for v in vs}
    m.freeSol(warm)
    trace, policy, gate, record, agent = [], None, None, None, None
    source_sha = sha(source)
    scope = 'initialization'
    prep_seconds = 0.
    if stage == 'prep':
        if case.get('shared'):
            trace, prep_seconds = prior['spbs_levels'], prior['initialization_wall_seconds']
        else:
            t0 = time.monotonic()
            vals, trace = improve_skeleton(x, vals, 60.)
            prep_seconds = time.monotonic() - t0
    else:
        m.setObjective(x.primary_objective if stage == 'A' else x.secondary_objective, 'minimize')
        m.setRealParam('limits/time', m.infinity())
        m.setRealParam('limits/gap', threshold)
        m.setRealParam('limits/absgap', 0.)
        scope = 'global_product_Cmax' if stage == 'A' else 'fixed_structure_secondary'
        if stage == 'A':
            m.addCons(x.cmax >= route_bound(x), name='mandatory_serial_AL_and_last_product_route')
            agent, policy = install_cpu(m, method)
        else:
            for v in vs:
                if v.vtype() != 'CONTINUOUS' and not v.name.startswith('sync_'):
                    val = round(vals[v.name])
                    m.chgVarLb(v,val)
                    m.chgVarUb(v,val)
            m.addCons(x.cmax <= cert['metrics']['cmax'] + 1.e-6, name='certified_handoff_cap')
        warm = as_sol(vals)
        if not m.checkSol(warm, printreason=True, completely=True, original=True):
            raise ValueError('Initial witness failed stage constraints')
        m.addSol(warm)
        resume_dir = folder / 'checkpoints'
        snapshots = sorted(resume_dir.glob('*/check.json'), reverse=True)
        restart = None
        if snapshots:
            restart = read(snapshots[0])
            if restart['input_sha256'] != source_sha or restart['scope'] != scope:
                raise ValueError('Checkpoint provenance mismatch')
            p = snapshots[0].parent / 'incumbent.json.gz'
            if sha(p) != restart['sha256']:
                raise ValueError('Changed restart witness')
            s = as_sol(witness(p,vs))
            if not m.checkSol(s, completely=True, original=True):
                raise ValueError('Restart incumbent rejected')
            m.addSol(s)
            if restart['lower'] is not None:
                m.addCons((x.primary_objective if stage == 'A' else x.secondary_objective) >= restart['lower'] - 1e-6)
        class Observer(scip.Eventhdlr):
            events = scip.SCIP_EVENTTYPE.BESTSOLFOUND | scip.SCIP_EVENTTYPE.DUALBOUNDIMPROVED | scip.SCIP_EVENTTYPE.NODESOLVED
            last = last_write = -1e9
            def eventinit(self):
                self.model.catchEvent(self.events,self)
            def eventexit(self):
                self.model.dropEvent(self.events,self)
            def eventexec(self,event):
                now = time.monotonic()
                if now-self.last < 5: return
                self.last = now
                lb, ub = finite(m.getDualbound()), finite(m.getPrimalbound())
                save(progress, dict(phase=stage, lower=lb, upper=ub, gap=finite(m.getGap()),
                                    seconds=now-started, nodes=m.getNNodes(), attempt=attempt.name))
                if now-self.last_write >= 120 and m.getNSols() and lb is not None and ub is not None and lb <= ub+1.e-6:
                    self.last_write = now
                    snap = resume_dir / str(time.time_ns())
                    best = m.getBestSol()
                    p = snap / 'incumbent.json.gz'
                    save(p, sparse({v.name:m.getSolVal(best,v) for v in vs}))
                    save(snap/'check.json', dict(input_sha256=source_sha,scope=scope,lower=lb,sha256=sha(p)))
                    # Keep the two last complete restart points.
                    for obsolete in sorted(resume_dir.glob('*/check.json'))[:-2]:
                        obsolete.unlink()
                        (obsolete.parent/'incumbent.json.gz').unlink()
                        obsolete.parent.rmdir()
                if psutil.virtual_memory().available < 2.0 * 1024**3:
                    self.model.interruptSolve()
        m.includeEventhdlr(Observer(), 'stage_observer', 'bounds and recoverable stage assignments')
        save(progress, dict(phase=stage, threshold=threshold, input=initial, attempt=attempt.name))
        m.optimize()
        record = stage_record(m, 'primary' if stage == 'A' else 'secondary', None)
        gate = gap_certificate(record, threshold)
        record.update(wall_seconds=time.monotonic()-started, original_scope=scope, resume=restart is not None)
        if agent is not None:
            save(attempt/'cutsel.json',agent.get_telemetry())
        save(attempt/'termination.json',dict(record=record,gate=gate))
        if not gate['accepted'] or gate['recomputed_gap'] is None or gate['recomputed_gap'] > threshold+1e-9:
            raise RuntimeError('Stage remains uncertified: '+str(record['status']))
        best = m.getBestSol()
        vals = {v.name:m.getSolVal(best,v) for v in vs}
        m.freeTransform()
    s = as_sol(vals)
    data, metrics = decode(s)
    if stage == 'B' and (metrics['cmax'] > initial['cmax']+EPS or metrics['secondary'] > initial['secondary']+EPS):
        raise ValueError('Handoff cap or secondary incumbent dominance failed')
    obj = 'cmax' if stage == 'A' else 'secondary'
    if record and abs(metrics[obj] - record['primal_bound']) > EPS:
        raise ValueError('Event metric disagrees with solver objective')
    save(folder/'assignment.json.gz', sparse(vals))
    save(folder/'schedule.json',data)
    save(folder/'evidence.json',dict(valid=True, case=case['id'], phase=stage, arm=arm, threshold=threshold,
        solver_seed=SEED, training_seed=TRAINING_SEED, scope=scope, source=rel(source),
        input_sha256=source_sha, assignment_sha256=sha(folder/'assignment.json.gz'), schedule_sha256=sha(folder/'schedule.json'),
        metrics=metrics, input_metrics=initial, gate=gate, record=record, policy=policy, trace=trace,
        prep_seconds=prep_seconds, elapsed=time.monotonic()-started, attempt=attempt.name))
