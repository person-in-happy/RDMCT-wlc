"""Isolated current-D primary search, optionally sharing GPU with existing jobs.

No fixed solver/RSS memory cap. No shared queue lock or shared LP export.
plan/prepare/check never optimize. Only start/run/resume launch a worker.
Global claims require the unrestricted primary bound to meet a verified incumbent.
"""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timezone
import argparse, hashlib, json, math, os, shutil, subprocess, sys, time

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT/'JMS-version/model4_pjob_nonprocessing_20261103'
RESULTS = ROOT/'JMS-version/results'
sys.path.insert(0, str(BACKEND))
from model import Config, Integrated
from validate import validate
from run_experiments import assets, digest, dump, finite, ports
from joint_algorithms import install, policy_record
from run_matched_supplement import output_lock
from scip_imports import scip


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def stamp():
    return datetime.now(timezone.utc).isoformat()


def inventory():
    paths = [Path(__file__), Path(__file__).with_name('large_schedule_plot.py'),
             Path(__file__).with_name('current_defaults_swimlane.py'),
             Path(__file__).with_name('render_current_defaults_gantt.py')]
    return assets() | {str(p.relative_to(ROOT)): digest(p) for p in paths}


def configuration(a):
    if not 1 <= a.size <= 100 or a.cleaning_interval < 2:
        raise ValueError('Use 1..100 products and cleaning interval >=2')
    return Config(ports(a.size, a.recipe), cleaning_interval=a.cleaning_interval,
                  dummy_count=a.dummy_count)


def capacity(cfg):
    n4 = sum(p['4x1'] for p in cfg.load_ports.values())
    n2 = sum(p['2x2'] for p in cfg.load_ports.values())
    n, productive = n4+n2, n4+2*n2
    # Every productive cycle has at most four product exposures. Between
    # cleanings at most H productive cycles; each chamber's final suffix
    # contains at most H-1 cycles because reaching H requires terminal clean.
    minimum_productive = math.ceil(productive/4)
    minimum_clean = max(0, math.ceil((minimum_productive-len(cfg.chambers)*(cfg.cleaning_interval-1))/cfg.cleaning_interval))
    return dict(products=n, mode_counts={'4x1':n4,'2x2':n2},
                full_candidate_pairs=n+3*productive,
                full_candidate_cycles_per_chamber=2*productive,
                necessary_minimum_productive_cycles=minimum_productive,
                necessary_minimum_cleaning_cycles=minimum_clean)


def proof_verdict(d):
    """Never inherit secondary, fixed-structure or restricted-domain optima."""
    cfg = d.get('config', {})
    lb, ub, gap = d.get('primary_bound'), d.get('cmax'), d.get('primary_gap')
    finite_number = lambda v: isinstance(v, (int, float)) and math.isfinite(v) and abs(v) < 1e19
    current = (cfg.get('module_residency'), cfg.get('robot_residency'), cfg.get('horizon'),
               cfg.get('chamber_residency_basis')) == (100,100,10000,'nonprocessing')
    valid = bool(current and d.get('solutions') and d.get('original_model_check') is True
                 and d.get('validation', {}).get('valid') is True)
    complete = (d.get('full_candidate_space') is True and d.get('restricted_candidate_bounds') is False
                and cfg.get('max_pairs') == cfg.get('max_cycles') == 0
                and d.get('experiment_scope') == 'joint' and d.get('phase') != 'secondary'
                and d.get('primary_objective') == 'product_return_cmax')
    optimal = bool(valid and complete and d.get('primary_status') == 'optimal'
                   and finite_number(lb) and finite_number(ub) and abs(lb-ub) <= 2e-4
                   and finite_number(gap) and abs(gap) <= 1e-8)
    products = [j for j in d.get('jobs', []) if j.get('product')]
    modes = {c['mode'] for c in d.get('cycles', [])}
    target = len(products) == 100 and {'4x1','2x2','clean'} <= modes
    return dict(valid=valid, full_primary_optimal=optimal,
                target_100_mixed_clean=target,
                target_global_optimal=optimal and target)


def configure_stopping(model, settings):
    """Strict mode has no time/node/solution-count termination criterion."""
    if settings.get('until_optimal'):
        for name in ('limits/time','limits/softtime','limits/nodes','limits/totalnodes',
                     'limits/stallnodes','limits/solutions','limits/bestsol',
                     'limits/restarts','limits/autorestartnodes','limits/primal','limits/dual'):
            if name in model.getParams():
                model.resetParam(name)
        if model.getParam('limits/time') < 1e19:
            raise RuntimeError('Native time limit is unexpectedly finite')
    else:
        model.setRealParam('limits/time', settings['time_limit'])
    model.setRealParam('limits/gap', 0)
    model.setRealParam('limits/absgap', 0)


def write_values(path, model, solution):
    """Stream the complete assignment; avoid a second huge Python value dict."""
    path = Path(path); temporary = path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w',encoding='utf-8',buffering=1024*1024) as f:
        f.write('{"values":{')
        first = True
        for var in model.getVars(transformed=False):
            if not first: f.write(',')
            first = False
            f.write(json.dumps(var.name)); f.write(':')
            f.write(json.dumps(float(model.getSolVal(solution,var)),allow_nan=False))
        f.write('}}\n')
    temporary.replace(path)


class IncumbentPublisher:
    """Commit immutable verified snapshots, then atomically advance a pointer."""
    def __init__(self,x,out):
        self.x=x;self.out=Path(out);self.best=float('inf');self.latest=None
        root=self.out/'incumbents'
        self.count=max((int(p.name) for p in root.iterdir() if p.is_dir() and p.name.isdigit()),
                       default=0) if root.exists() else 0
        if (self.out/'latest_incumbent.json').exists():
            pointer=read(self.out/'latest_incumbent.json')
            self.latest=(self.out/pointer['snapshot']).resolve()
            if not self.latest.is_relative_to(root.resolve()):
                raise ValueError('Saved incumbent outside this campaign')
            cert=read(self.latest/'certificate.json')
            if cert['campaign_sha256']!=digest(self.out/'campaign.json'):
                raise ValueError('Saved incumbent belongs to another campaign')
            for name in ('result','variables'):
                if digest(self.latest/(name+'.json'))!=cert[name+'_sha256']:
                    raise ValueError('Saved incumbent was changed')
            self.best=float(read(self.latest/'result.json')['cmax'])

    def publish(self,solution,final=False):
        x=self.x;m=x.model
        cmax=float(m.getSolVal(solution,x.cmax))
        if final and cmax > self.best+1e-6:
            raise RuntimeError('Final incumbent is worse than the saved warm start')
        if not final and cmax >= self.best-1e-6:
            return None
        if not m.checkSol(solution,printreason=False,completely=True,original=True):
            raise RuntimeError('Live incumbent rejected by complete original model')
        data=x.result(solution=solution)
        physical=validate(data)
        if not physical['valid']:
            raise RuntimeError('Live incumbent rejected by physical replay: '+str(physical['errors'][:5]))
        solving=m.getStage() >= scip.SCIP_STAGE.SOLVING
        bound=m.getDualbound() if solving else None
        gap=m.getGap() if solving else None
        state=str(m.getStatus()) if final else 'solving'
        data.update(status=state,original_model_check=True,full_candidate_space=True,
                    experiment_scope='joint',primary_status=state,primary_bound=bound,primary_gap=gap,
                    primary_objective='product_return_cmax',validation=physical,
                    solve_seconds=m.getSolvingTime(),snapshot_phase='final' if final else 'incumbent')
        verdict=proof_verdict(data);data['global_optimality_claim']=verdict['full_primary_optimal']
        self.count+=1
        dest=self.out/'incumbents'/f'{self.count:06d}'
        dest.mkdir(parents=True,exist_ok=False)
        dump(dest/'result.json',finite(data))
        write_values(dest/'variables.json',m,solution)
        certificate=dict(verdict=verdict,status=state,cmax=cmax,primary_bound=bound,primary_gap=gap,
                         result_sha256=digest(dest/'result.json'),variables_sha256=digest(dest/'variables.json'),
                         campaign_sha256=digest(self.out/'campaign.json'),
                         original_model_check=True,independent_physical_check=physical,
                         full_candidate_space=True,sequence=self.count,created_utc=stamp())
        dump(dest/'certificate.json',finite(certificate))
        pointer=dict(snapshot=dest.relative_to(self.out).as_posix(),sequence=self.count,cmax=cmax,
                     certified_global_optimal=verdict['full_primary_optimal'],created_utc=stamp())
        dump(self.out/'latest_incumbent.json',pointer)
        self.best=cmax
        self.latest=dest
        print('VERIFIED_INCUMBENT '+json.dumps(pointer),flush=True)
        return dest


class PublishBestSolution(scip.Eventhdlr):
    def __init__(self,publisher):
        self.publisher=publisher

    def eventinit(self):
        self.model.catchEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND,self)

    def eventexit(self):
        self.model.dropEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND,self)

    def eventexec(self,event):
        try:
            self.publisher.publish(self.model.getBestSol())
        except Exception as exc:
            # Never let Python exceptions escape into SCIP's C callback.
            dump(self.publisher.out/'incumbent_export_error.json',
                 dict(error=repr(exc),created_utc=stamp()))
            print('INCUMBENT_EXPORT_FAILED '+repr(exc),flush=True)
            self.model.interruptSolve()


def safe_out(value):
    out = Path(value).resolve()
    if out == RESULTS or not out.is_relative_to(RESULTS):
        raise ValueError('Use an isolated child directory of JMS-version/results')
    return out


def prepare(a, out):
    import psutil
    if out.exists():
        raise FileExistsError('Output exists; use run/resume or a new campaign')
    if not 0 < a.min_available_fraction < .5 or (not a.until_optimal and
            (a.time_limit <= 0 or a.wall_limit <= a.time_limit)):
        raise ValueError('Positive solve budget, longer wall guard, and RAM fraction in (0,.5) required')
    cfg = configuration(a)
    record = policy_record(a.method, a.training_seed)
    warm = None
    if a.warm_start:
        path = Path(a.warm_start).resolve()
        source = read(path.parent/'result.json')
        if json.loads(json.dumps(asdict(cfg))) != source['config']:
            raise ValueError('Warm-start input must be exactly this instance')
        if not source.get('original_model_check') or not validate(source)['valid']:
            raise ValueError('Warm source has no accepted current-model witness')
        warm = dict(path=str(path), sha256=digest(path))
    out.mkdir(parents=True)
    dump(out/'config.json', asdict(cfg))
    peers = []
    for p in psutil.process_iter(['pid','name','cmdline']):
        try:
            cmd = p.info['cmdline'] or []
            if p.pid != os.getpid() and p.info['name'].lower().startswith('python') and any(
                'journal_support_experiments.py' in x or 'thesis_gap_experiments.py' in x for x in cmd):
                peers.append(dict(pid=p.pid, command=cmd))
        except (psutil.Error, AttributeError):
            pass
    settings = dict(time_limit=None if a.until_optimal else a.time_limit,
                    wall_limit=None if a.until_optimal else a.wall_limit,
                    until_optimal=a.until_optimal,live_gantt=True,
                    min_available_fraction=a.min_available_fraction,
                    memory_policy='native_unlimited_with_system_available_fraction',
                    fixed_scip_memory_mb=None, fixed_process_rss_mb=None,
                    threads=1, new_workers=1, method=a.method,
                    training_seed=a.training_seed, seed=a.seed, gpu_device=a.gpu_device,
                    concurrent_with_existing=True, stage2_limit=0)
    spec = dict(schema=1, created_utc=stamp(), config_sha256=digest(out/'config.json'),
                settings=settings, assets=inventory(), policy=record, warm_start=warm,
                instance=capacity(cfg), concurrent_processes_at_prepare=peers,
                scope='Unrestricted current D primary Cmax problem; no witness restrictions',
                inference='Optimization attempt, not a matched-time algorithm benchmark',
                machine=dict(total_ram_bytes=psutil.virtual_memory().total,
                             available_ram_bytes=psutil.virtual_memory().available,
                             logical_cpus=psutil.cpu_count()))
    dump(out/'campaign.json', spec)
    dump(out/'contract.json', dict(campaign_sha256=digest(out/'campaign.json')))
    for rel in spec['assets']:
        target = out/'frozen_code'/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/rel, target)
    print(json.dumps(dict(prepared=str(out), instance=spec['instance'], settings=settings,
                          solver_started=False), ensure_ascii=False), flush=True)


def checked(out):
    spec = read(out/'campaign.json')
    if digest(out/'campaign.json') != read(out/'contract.json')['campaign_sha256']:
        raise RuntimeError('Frozen protocol changed')
    if digest(out/'config.json') != spec['config_sha256'] or inventory() != spec['assets']:
        raise RuntimeError('Frozen input/code changed; use a new campaign')
    st = spec['settings']
    if policy_record(st['method'], st['training_seed']) != spec['policy']:
        raise RuntimeError('Frozen policy changed')
    warm = spec['warm_start']
    if warm and digest(Path(warm['path'])) != warm['sha256']:
        raise RuntimeError('Warm assignment changed')
    return spec


def status(out):
    spec=checked(out)
    dest = out/'solve'
    if (dest/'failure.json').exists():
        return dict(complete=0, failed=1, pending=0, failure=read(dest/'failure.json'),
                    best_saved=read(out/'latest_incumbent.json') if (out/'latest_incumbent.json').exists() else None)
    if (dest/'certificate.json').exists() and (dest/'resources.json').exists():
        cert = read(dest/'certificate.json')
        if cert.get('campaign_sha256') != digest(out/'campaign.json'):
            raise RuntimeError('Certificate belongs to a different campaign')
        if digest(dest/'result.json') != cert['result_sha256']:
            raise RuntimeError('Result changed')
        if spec.get('settings',{}).get('until_optimal') and not proof_verdict(read(dest/'result.json'))['target_global_optimal']:
            return dict(complete=0,failed=1,pending=0,state=cert['status'],
                        reason='proven_infeasible' if cert['status']=='infeasible' else 'global_optimum_not_proven',
                        best_saved=read(out/'latest_incumbent.json') if (out/'latest_incumbent.json').exists() else None)
        return dict(complete=1, failed=0, pending=0, **cert['verdict'],
                    cmax=cert['cmax'], bound=cert['primary_bound'], state=cert['status'])
    return dict(complete=0, failed=0, pending=1,
                best_saved=read(out/'latest_incumbent.json') if (out/'latest_incumbent.json').exists() else None)


def worker(out):
    spec = checked(out); st = spec['settings']; dest = out/'solve'
    dest.mkdir(parents=True, exist_ok=False)
    cfg = Config(**read(out/'config.json'))
    print('BUILD complete current D: '+json.dumps(capacity(cfg)), flush=True)
    started = time.monotonic()
    x = Integrated(cfg); m = x.model
    try:
        native_memory = m.getParam('limits/memory')
        if native_memory < 1e12:
            raise RuntimeError('SCIP native memory is capped unexpectedly')
        dump(dest/'build.json', dict(dimensions=x.original_dimensions, seconds=time.monotonic()-started,
                                     safe_bounds=x.safe_bounds, restricted=x.bounded,
                                     native_memory_parameter=native_memory))
        assert not x.bounded and cfg.max_pairs == cfg.max_cycles == 0
        m.setIntParam('parallel/maxnthreads', 1)
        m.setIntParam('randomization/randomseedshift', st['seed'])
        configure_stopping(m,st)
        m.setLogfile(str(dest/'solver.log')); m.hideOutput(False)
        publisher=IncumbentPublisher(x,out)
        events=PublishBestSolution(publisher)
        m.includeEventhdlr(events,'publish_verified_incumbents','Save and expose complete validated improving schedules')
        warm_path=(publisher.latest/'variables.json') if publisher.latest else (
                  Path(spec['warm_start']['path']) if spec['warm_start'] else None)
        if warm_path:
            values = read(warm_path)['values']
            sol = m.createSol()
            for v in m.getVars(transformed=False):
                m.setSolVal(sol, v, values[v.name])
            if not m.checkSol(sol, printreason=True, completely=True, original=True):
                m.freeSol(sol)
                raise RuntimeError('Warm assignment rejected by complete original model')
            publisher.publish(sol)
            if not m.addSol(sol):
                raise RuntimeError('Verified warm start was not retained by SCIP')
            del values
        agent, policy = install(m, st['method'], st['training_seed'])
        if agent is not None:
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError('Requested GPU policy but CUDA is unavailable')
            dump(dest/'gpu.json', dict(device=os.environ.get('CUDA_VISIBLE_DEVICES'),
                                       name=torch.cuda.get_device_name(0), policy=policy))
        dump(dest/'termination_settings.json',
             {k:v for k,v in m.getParams().items() if k.startswith('limits/')})
        optimize_started = time.monotonic()
        m.optimize()
        d = x.result()
        accepted = bool(m.getNSols() and m.checkSol(m.getBestSol(), printreason=False,
                                                   completely=True, original=True))
        d.update(original_model_check=accepted, full_candidate_space=True,
                 experiment_scope='joint', primary_status=d['status'],
                 primary_bound=d.get('dual_bound'), primary_gap=d.get('gap'),
                 primary_objective='product_return_cmax', method=st['method'],
                 initialization='verified_warm' if warm_path else 'none',
                 warm_start_path=str(warm_path) if warm_path else None,
                 optimization_wall_seconds=time.monotonic()-optimize_started)
        d['validation'] = validate(d)
        verdict = proof_verdict(d)
        d.update(result_eligible=verdict['valid'], global_optimality_claim=verdict['full_primary_optimal'])
        dump(dest/'result.json', finite(d))
        if m.getNSols():
            solution = m.getBestSol()
            snapshot=publisher.publish(solution,final=True)
            shutil.copy2(snapshot/'variables.json',dest/'variables.json')
            m.writeBestSol(str(dest/'solution.sol'))
        if agent is not None:
            dump(dest/'cutsel_telemetry.json', agent.get_telemetry())
        certificate = dict(verdict=verdict, status=d['status'], cmax=d.get('cmax'),
                           primary_bound=d.get('primary_bound'), primary_gap=d.get('primary_gap'),
                           result_sha256=digest(dest/'result.json'), campaign_sha256=digest(out/'campaign.json'),
                           original_model_check=accepted, independent_physical_check=d['validation'],
                           full_candidate_space=True, optimization_calls=1,
                           wall_seconds=time.monotonic()-started,
                           scope='Primary Cmax only; no fixed structure or extra cleaning constraint')
        if (dest/'variables.json').exists():
            certificate['variables_sha256'] = digest(dest/'variables.json')
        dump(dest/'certificate.json', finite(certificate))
        print(json.dumps(finite(certificate), ensure_ascii=False), flush=True)
        if m.getNSols() and not verdict['valid']:
            raise RuntimeError('Incumbent rejected; retained for diagnosis, not for plotting')
    finally:
        m.freeProb()


def run(out, retry_failed=False):
    import psutil
    spec = checked(out); st = spec['settings']; dest = out/'solve'
    # Lock only this output. Existing journal/thesis experiments remain running.
    with output_lock(out):
        if dest.exists():
            if status(out)['complete']:
                print(json.dumps(status(out))); return
            if not retry_failed:
                raise RuntimeError('Incomplete attempt retained; inspect it before --retry-failed')
            archive = out/'interrupted_attempts'/str(time.time_ns())
            if dest.is_symlink() or not dest.resolve().is_relative_to(out) or not archive.resolve().is_relative_to(out):
                raise ValueError('Unsafe archive path')
            archive.parent.mkdir(exist_ok=True); dest.rename(archive)
        vm = psutil.virtual_memory()
        if vm.available/vm.total < st['min_available_fraction']:
            raise RuntimeError('RESOURCE_INSUFFICIENT: available RAM '
                               f'{vm.available/1024**3:.2f} GiB < {st["min_available_fraction"]:.0%} '
                               'of total RAM; no worker started')
        env = os.environ.copy()
        env.update(OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   CUDA_VISIBLE_DEVICES=str(st['gpu_device']))
        logpath = out/f'foreground_{time.time_ns()}.log'
        begin = time.monotonic(); peak = 0; minimum = 1.; reason = None; last = -10.
        guard_snapshot = None
        renderer = None; renderer_log = None; rendering_key = None
        rendered_key = None; next_render_attempt = 0.
        flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 0
        def refresh_gantt():
            nonlocal renderer,renderer_log,rendering_key,rendered_key,next_render_attempt
            if renderer is not None and renderer.poll() is not None:
                renderer_log.close()
                if renderer.returncode == 0:
                    rendered_key=rendering_key
                    print('GANTT_UPDATED '+str(out/'figures'/'gantt_resources.pdf'),flush=True)
                else:
                    next_render_attempt=time.monotonic()+60
                    print('GANTT_UPDATE_PENDING: inspect plot log; close any PDF that prevents replacement',flush=True)
                renderer=None;renderer_log=None
            if renderer is not None or time.monotonic()<next_render_attempt:
                return
            pointer_file=out/'latest_incumbent.json'
            if not pointer_file.exists():
                return
            pointer=read(pointer_file);key=pointer['snapshot']
            if key==rendered_key:
                return
            log=out/f'plot_{pointer["sequence"]:06d}.log'
            renderer_log=log.open('ab')
            renderer=subprocess.Popen([sys.executable,'-X','utf8','-u',str(Path(__file__)),
                    '_render','--campaign',str(out),'--snapshot',str(out/key)],
                    cwd=ROOT,env=env,stdout=renderer_log,stderr=subprocess.STDOUT,creationflags=flags)
            rendering_key=key
        print('START isolated current-D search; existing jobs continue; GPU may be shared; '
              +('NO TIME/NODE LIMIT; success requires global optimum' if st.get('until_optimal')
                else 'finite-budget mode'), flush=True)
        with logpath.open('wb') as log:
            child = subprocess.Popen([sys.executable,'-X','utf8','-u',str(Path(__file__)),
                                      '_worker','--campaign',str(out)], cwd=ROOT, env=env,
                                     stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
            try:
                while child.poll() is None:
                    elapsed = time.monotonic()-begin; vm = psutil.virtual_memory()
                    minimum = min(minimum, vm.available/vm.total)
                    try:
                        proc = psutil.Process(child.pid)
                        rss = sum(p.memory_info().rss for p in [proc]+proc.children(recursive=True))/1024**2
                    except psutil.Error:
                        rss = 0
                    peak = max(peak,rss)
                    if vm.available/vm.total < st['min_available_fraction']:
                        reason = 'system_available_memory_guard'
                        guard_snapshot=dict(available_mib=vm.available/1024**2,total_mib=vm.total/1024**2,
                                            required_available_fraction=st['min_available_fraction'])
                        print('RESOURCE_INSUFFICIENT: available RAM '
                              f'{vm.available/1024**3:.2f} GiB < '
                              f'{st["min_available_fraction"]:.0%} of total RAM; stopping ONLY the new solve',
                              flush=True)
                    if st['wall_limit'] is not None and elapsed > st['wall_limit']:
                        reason = 'wall_guard'
                    if reason:
                        child.terminate(); break
                    if elapsed-last >= 10:
                        budget=('none' if st['wall_limit'] is None else
                                f'{max(0,st["wall_limit"]-elapsed)/3600:.2f}h')
                        print(f'complete=0/1 failed=0 running=1 elapsed={elapsed:.0f}s RSS={rss:.0f}MiB '
                              f'system_available={vm.available/vm.total:.1%} '
                              f'wall_budget_remaining={budget} '
                              f'optimality_ETA=unknown', flush=True)
                        last = elapsed
                    refresh_gantt()
                    time.sleep(.5)
            except KeyboardInterrupt:
                reason = 'foreground_interrupted'; child.terminate()
            finally:
                try:
                    code = child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    child.kill(); code = child.wait(timeout=30)
        # Finish the latest committed snapshot even after a resource stop.
        # The separate plotting helper never reads the live SCIP object.
        plot_deadline=time.monotonic()+60
        while time.monotonic()<plot_deadline:
            refresh_gantt()
            if renderer is None:
                break
            time.sleep(.5)
        if renderer is not None:
            renderer.terminate();renderer.wait(timeout=30);renderer_log.close()
            print('GANTT_UPDATE_PENDING: saved snapshot can be rendered with the render command',flush=True)
        dest.mkdir(exist_ok=True)
        dump(dest/'resources.json', dict(exit_code=code, peak_rss_mib=peak, wall_seconds=time.monotonic()-begin,
                minimum_system_available_fraction=minimum, memory_policy=st['memory_policy'],
                concurrent_with_existing=True, log=str(logpath),guard_snapshot=guard_snapshot))
        if not reason and code == 0 and (dest/'certificate.json').exists() and st.get('until_optimal'):
            cert=read(dest/'certificate.json')
            if not cert['verdict']['target_global_optimal']:
                reason='proven_infeasible' if cert['status']=='infeasible' else 'global_optimum_not_proven'
                print('PROVEN_INFEASIBLE: no schedule for this instance' if reason=='proven_infeasible'
                      else 'PROOF_INCOMPLETE: latest feasible Gantt retained; this is not a successful optimality run',
                      flush=True)
        if reason or code or not (dest/'certificate.json').exists():
            if not reason:
                with logpath.open('rb') as f:
                    f.seek(max(0,logpath.stat().st_size-8192))
                    tail=f.read().decode('utf-8',errors='replace')
                reason='resource_allocation_failed' if any(word in tail for word in
                    ('MemoryError','out of memory','No memory','RESOURCE_INSUFFICIENT','No space left')) else 'worker_exit'
            if reason=='resource_allocation_failed':
                print('RESOURCE_INSUFFICIENT: memory/VRAM/disk allocation failed; '
                      'saved incumbents and Gantt retained. See '+str(logpath),flush=True)
            dump(dest/'failure.json', dict(reason=reason, exit_code=code, log=str(logpath),
                                          guard_snapshot=guard_snapshot))
            print('complete=0/1 failed=1; attempt preserved', flush=True)
            raise RuntimeError(reason+': new worker stopped; existing workers were not terminated')
        print(json.dumps(status(out), ensure_ascii=False), flush=True)


def render(out, require_optimal=False, snapshot=None):
    checked(out); dest = out/'solve'
    if snapshot is None and (out/'latest_incumbent.json').exists():
        snapshot=out/read(out/'latest_incumbent.json')['snapshot']
    if snapshot is not None:
        dest=Path(snapshot).resolve()
        if not dest.is_relative_to(out/'incumbents'):
            raise ValueError('Snapshot must belong to this campaign')
    if not (dest/'certificate.json').exists():
        raise ValueError('No completely saved feasible incumbent yet; no schedule to draw')
    cert=read(dest/'certificate.json')
    if cert.get('campaign_sha256')!=digest(out/'campaign.json'):
        raise RuntimeError('Certificate belongs to a different campaign')
    for name,key in [('result.json','result_sha256'),('variables.json','variables_sha256')]:
        if digest(dest/name) != cert.get(key):
            raise RuntimeError('Changed result or assignment')
    d = read(dest/'result.json'); physical = validate(d); verdict = proof_verdict(d)
    if d['config'] != read(out/'config.json'):
        raise ValueError('Result configuration differs from the frozen input')
    if not physical['valid'] or not verdict['valid'] or not verdict['target_100_mixed_clean']:
        raise ValueError('Need 100 validated products and actual 4x1/2x2/clean cycles')
    if require_optimal and not verdict['target_global_optimal']:
        raise ValueError('Full primary optimum is unproved; omit --require-optimal for a feasible preview')
    from large_schedule_plot import draw
    figures=out/'figures';figures.mkdir(exist_ok=True)
    with output_lock(figures):
        if (figures/'manifest.json').exists():
            previous=read(figures/'manifest.json')
            if previous.get('cmax',float('inf')) < d['cmax']-1e-6:
                return
            if (abs(previous.get('cmax',float('inf'))-d['cmax'])<=1e-6
                    and previous['verdict']['target_global_optimal']
                    and not verdict['target_global_optimal']):
                return
        staging=figures/'.pending_render'
        draw(d,staging,verdict['target_global_optimal'])
        dump(staging/'manifest.json', dict(source=str(dest/'result.json'),
             result_sha256=cert['result_sha256'],variables_sha256=cert['variables_sha256'],
             certificate_sha256=digest(dest/'certificate.json'),
             campaign_sha256=digest(out/'campaign.json'),verdict=verdict,cmax=d['cmax'],
             updated_utc=stamp(),optimization_calls=0))
        for path in staging.iterdir():
            if path.name!='manifest.json':
                path.replace(figures/path.name)
        (staging/'manifest.json').replace(figures/'manifest.json')
        staging.rmdir()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('action', choices=['plan','prepare','check','start','run','resume','status','render','_worker','_render'])
    p.add_argument('--campaign'); p.add_argument('--size', type=int, default=100)
    p.add_argument('--recipe', choices=['4x1','2x2','mixed'], default='mixed')
    p.add_argument('--cleaning-interval', type=int, default=3); p.add_argument('--dummy-count',type=int,default=8)
    p.add_argument('--method', choices=['scip','hem','proposed'], default='proposed')
    p.add_argument('--training-seed',type=int,default=1); p.add_argument('--seed',type=int,default=1)
    p.add_argument('--gpu-device',type=int,default=0)
    p.add_argument('--time-limit',type=float,default=86400); p.add_argument('--wall-limit',type=float,default=108000)
    p.add_argument('--until-optimal',action='store_true')
    p.add_argument('--min-available-fraction',type=float,default=.25)
    p.add_argument('--warm-start'); p.add_argument('--retry-failed',action='store_true')
    p.add_argument('--allow-feasible',action='store_true'); p.add_argument('--require-optimal',action='store_true')
    p.add_argument('--snapshot')
    a = p.parse_args()
    if a.allow_feasible and a.require_optimal:
        p.error('Choose feasible preview OR optimal-only rendering')
    if a.until_optimal and any(v.split('=')[0] in ('--time-limit','--wall-limit') for v in sys.argv[2:]):
        p.error('--until-optimal has no time/wall limit; do not combine with finite budgets')
    if a.retry_failed and a.action != 'resume':
        p.error('--retry-failed only applies to resume')
    if a.action == 'plan':
        print(json.dumps(dict(instance=asdict(configuration(a)),capacity=capacity(configuration(a)),
                              method=a.method,solver_started=False),ensure_ascii=False,indent=2)); return
    if not a.campaign: p.error('--campaign required')
    out = safe_out(a.campaign)
    if a.action not in ('prepare','start'):
        frozen = ('--size','--recipe','--cleaning-interval','--dummy-count','--method','--training-seed',
                  '--seed','--gpu-device','--time-limit','--wall-limit','--min-available-fraction','--warm-start','--until-optimal')
        if any(v.split('=')[0] in frozen for v in sys.argv[2:]):
            p.error('Protocol frozen; prepare a new campaign to change settings')
    if a.action in ('prepare','start'): prepare(a,out)
    if a.action in ('start','run','resume'): run(out,a.retry_failed)
    elif a.action == 'status': print(json.dumps(status(out),ensure_ascii=False))
    elif a.action == '_worker': worker(out)
    elif a.action in ('render','_render'): render(out,a.require_optimal,a.snapshot)
    elif a.action == 'check':
        st = checked(out)['settings']
        os.environ['CUDA_VISIBLE_DEVICES'] = str(st['gpu_device'])
        from scip_imports import scip
        m = scip.Model()
        try:
            configure_stopping(m,st)
            agent,policy = install(m,st['method'],st['training_seed'])
            gpu = None
            if agent is not None:
                import torch
                if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
                gpu = torch.cuda.get_device_name(0)
            print(json.dumps(dict(config_valid=True,policy_loaded=policy,gpu=gpu,
                                  termination={name:m.getParam(name) for name in
                                      ('limits/time','limits/nodes','limits/solutions',
                                       'limits/gap','limits/absgap','limits/memory')},
                                  wall_limit=st['wall_limit'],
                                  model_built=False,solver_started=False),ensure_ascii=False))
        finally: m.freeProb()


if __name__ == '__main__':
    main()
