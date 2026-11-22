"""Low-memory D75 search and a separate, unrestricted chamber/VTR lower bound."""
import math
from pathlib import Path
import sys
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'scale75_continue_20261120'))
import check_6061 as original
import continue_primary as continuation
import chamber_bound
from ortools.sat.python import cp_model
sys.path.insert(0, str(HERE.parent/'sublevel_bounds_20261120'))
from bounds import capacity, lock_bound

first, old = original.first, original.old
OUT = old.JMS/'results/manuscript_projection_20261120_r1/scale75'
TARGET = .00001


def robot_relaxation(cfg, upper, source, prior, capacity_plan):
    """Keep necessary chamber and cross-chamber robot constraints for every original schedule."""
    cp = cp_model.CpModel()
    horizon = int(upper)
    finish = cp.new_int_var(prior, horizon, 'last_product')
    qmax = capacity_plan['cycles']
    h, rot, travel = map(int, (cfg.handling, cfg.rotation, cfg.vtr_travel))
    retained, fresh = rot+2*h, 2*h+rot+max(2*h+rot,3*h+2*travel)
    locks = lock_bound(cfg)
    arrival = [0]+[int(a+cfg.atr_handling+cfg.pump+2*h+travel) for a in locks['entries']]
    loads, mixed, robots, known = [], [], [], {}
    product_pairs = {p['id']:sum(j['product'] for j in source['jobs'] if j['pair']==p['id'])
                     for p in source['pairs']}
    def var(lo, hi, name, value=None):
        result = cp.new_int_var(lo, hi, name)
        if value is not None:
            known[result.index] = int(round(value))
        return result
    for chamber in cfg.chambers:
        seq = sorted((c for c in source['cycles'] if c['chamber']==chamber), key=lambda c:c['index'])
        while seq and seq[-1]['mode']=='clean':
            seq.pop()
        old_used, old_end, old_wash, old_count, old_enter = 1, 0, 0, 0, 0
        cumulative = 0
        for q in range(qmax):
            name = f'{chamber}_{q}_'
            cycle = seq[q] if q<len(seq) else None
            mode = cycle['mode'] if cycle else ''
            used = var(0,1,name+'used',bool(cycle))
            full = var(0,1,name+'full',mode=='4x1')
            recipe = var(0,1,name+'mixed',mode=='2x2')
            wash = var(0,1,name+'wash',mode=='clean')
            t = var(0,horizon,name+'start',cycle['start'] if cycle else 0)
            end = var(0,horizon,name+'end',cycle['end'] if cycle else 0)
            continued = set(seq[q-1]['pairs']) if q and cycle else set()
            incoming = [p for p in (cycle['pairs'] if cycle else []) if p not in continued and product_pairs[p]]
            number = sum(product_pairs[p] for p in incoming)
            nf = var(0,4,name+'new_full_products',number if mode=='4x1' else 0)
            nm = var(0,2,name+'new_mixed_products',number if mode=='2x2' else 0)
            enter = var(0,1,name+'first_exposure',bool(number and mode=='2x2'))
            count = var(0,cfg.cleaning_interval,name+'count',cycle['counter'] if cycle else 0)
            cp.add(full+recipe+wash==used)
            cp.add(used<=old_used)
            cp.add(wash+old_wash<=1)
            cp.add(end==t+int(cfg.full_time)*full+int(cfg.mix_time)*recipe+int(cfg.cleaning_time)*wash)
            cp.add(t==0).only_enforce_if(used.Not())
            cp.add(finish>=end+int(capacity_plan['tail'])).only_enforce_if([used,wash.Not()])
            cp.add(nf>=full)
            cp.add(nf<=4*full)
            cp.add(nm>=enter)
            cp.add(nm<=2*enter)
            cp.add(enter<=recipe)
            cp.add(old_enter<=recipe)
            cp.add(enter+old_enter>=recipe)
            cp.add(count==old_count+1).only_enforce_if([used,wash.Not()])
            cp.add(count==0).only_enforce_if(wash)
            cp.add(count==0).only_enforce_if(used.Not())
            cumulative += nf+nm
            delivered = var(0,len(arrival)-1,name+'delivered')
            cp.add(delivered==cumulative)
            available = var(0,horizon,name+'available')
            cp.add_element(delivered,arrival,available)
            cp.add(t>=available).only_enforce_if(used)
            if q:
                cp.add(t>=old_end+retained).only_enforce_if(used)
                cp.add(t>=old_end+fresh).only_enforce_if([used,old_enter.Not()])
                # Between consecutive cycles every schedule unloads/loads at least one pair.
                # With no retained pair both old pairs leave and both new pairs enter.
                for action in range(4):
                    active = used if action < 2 else var(0,1,name+f'fresh_{action}')
                    if action >= 2:
                        cp.add(active==used-old_enter)
                    begin = var(0,horizon,name+f'robot_{action}')
                    cp.add(begin>=old_end).only_enforce_if(active)
                    cp.add(begin+h<=t).only_enforce_if(active)
                    robots.append(cp.new_optional_fixed_size_interval_var(begin,h,active,name+f'vtr_{action}'))
            else:
                cp.add(wash==0)
            if q==qmax-1:
                cp.add(enter==0)
            old_used, old_end, old_wash, old_count, old_enter = used,end,wash,count,enter
            loads.append(nf)
            mixed.append(nm)
    cp.add(sum(loads)==sum(p.get('4x1',0) for p in cfg.load_ports.values()))
    cp.add(sum(mixed)==sum(p.get('2x2',0) for p in cfg.load_ports.values()))
    cp.add_no_overlap(robots)
    cp.minimize(finish)
    cp.add_hint(finish,horizon)
    for index,value in known.items():
        cp.add_hint(cp.get_int_var_from_proto_index(index),value)
    if cp.validate():
        raise ValueError(cp.validate())
    sanity = cp_model.CpSolver()
    sanity.parameters.num_search_workers=1
    sanity.parameters.fix_variables_to_their_hinted_value=True
    sanity.parameters.max_time_in_seconds=30
    if sanity.solve(cp) not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        raise ValueError('Frozen physical witness did not embed in the global relaxation')
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=300
    solver.parameters.max_memory_in_mb=512
    solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    path=OUT/'bound_solver.log'
    with path.open('w',encoding='utf-8',buffering=1) as stream:
        solver.log_callback=lambda message:stream.write(message.rstrip()+'\n')
        status=solver.solve(cp)
    if status in (cp_model.INFEASIBLE,cp_model.MODEL_INVALID):
        raise ValueError('Relaxation excluded a verified feasible witness')
    return dict(lower=max(prior,solver.best_objective_bound),original_lower=prior,status=solver.status_name(status),
                solver_s=solver.wall_time,checkpoint_sanity=sanity.status_name(sanity.response_proto.status),
                vars=len(cp.proto.variables),rows=len(cp.proto.constraints),shared_robot_intervals=len(robots))


def execute():
    from gantt import draw
    first.limit_process()
    start=time.monotonic()
    case=original.DEST
    frozen=old.read(case/'report.json')
    data=old.read(case/'result.json')
    if frozen['retimed_result_sha256']!=old.digest(case/'result.json'):
        raise ValueError('75-wafer input hash mismatch')
    source=original.RUN.parent/old.read(original.RUN/'run_manifest.json')['source_case']
    with patch.object(first,'BASE',source):
        cfg,blocks,_=first.restore_seed()
    records=old.restore(source/'windows.json',old.read(source/'summary.json')['protocol_sha256'])
    events,cycles=iter(data['events']),iter(data['cycles'])
    initial=[int((next(cycles) if action.kind=='exposure' else next(events))['start']) for group in blocks for action in group.actions]
    if first.fixed_timing(cfg,blocks,initial).schedule(initial)!=data:
        raise ValueError('Rebuilt large input differs from archived witness')
    plan=capacity(cfg,data['cmax'])
    lower=chamber_bound.compute(cfg)['lower_s']
    if lower!=frozen['full_model_makespan_lower_s']:
        raise ValueError('Independent chamber lower bound mismatch')
    spec=dict(input=old.digest(case/'result.json'),threshold=TARGET,seconds_global_relaxation=300,
              workers=1,process_cap_mib=1024,scope='mixed case scheduling demonstration',
              per_window_sweeps=first.prior.SWEEPS,script=old.digest(Path(__file__)),capacity=plan)
    token=old.fingerprint(spec)
    with old.output_lock(OUT):
        if (OUT/'protocol.json').exists() and old.fingerprint(old.read(OUT/'protocol.json'))!=token:
            raise ValueError('Changed D75 protocol')
        old.dump(OUT/'protocol.json',spec)
        if (OUT/'evidence.json').exists():
            return
        if not (OUT/'bound.json').exists():
            print('D75 0/3, failed 0 | solving two chambers and shared VTR relaxation | budget 300 s',flush=True)
            old.dump(OUT/'bound.json',robot_relaxation(cfg,data['cmax'],data,lower,plan))
        lower=old.read(OUT/'bound.json')['lower']
        if not (OUT/'windows.json').exists():
            old.checkpoint(OUT/'windows.json',token,dict(plan=records['plan'],starts=initial,initial_cmax=data['cmax'],
                           sweep=0,index=0,windows=[],records=[]))
        runner=continuation.runner
        print(f'D75 1/3, failed 0 | global lower {lower} s, starting restartable makespan windows',flush=True)
        with patch.multiple(runner,A_GAP=TARGET,B_GAP=TARGET,OUT=OUT),runner.settings():
            state,blocks=first.prior.optimize(OUT,token,first.Search(cfg),{'cmax':data['cmax']},lower,None)
        times=state['starts']
        timings=first.fixed_timing(cfg,blocks,times)
        earliest=original.earliest_times(timings)
        engine=first.ChamberIdle(cfg,blocks)
        times=min((initial,times,earliest),key=lambda t:(engine.finish(t),engine.measure(t)['idle']))
        candidate,physical,replay,lanes=first.check_schedule(engine,blocks,times)
        gap=(physical['cmax']-lower)/lower
        if gap<=TARGET:
            with patch.multiple(runner,A_GAP=TARGET,B_GAP=TARGET,OUT=OUT),runner.settings():
                proposal,_=engine.solve_idle(times,engine.measure(times),lower,first.FIXED,40)
            times=min((times,proposal),key=lambda t:(engine.finish(t),engine.measure(t)['idle']))
            candidate,physical,replay,lanes=first.check_schedule(engine,blocks,times)
            gap=(physical['cmax']-lower)/lower
        print('D75 2/3, failed 0 | full streaming row audit and Gantt',flush=True)
        old.dump(OUT/'result.json',candidate)
        cert=first.prior.audit_result(OUT,token,candidate)
        figs=OUT/'figures'
        figs.mkdir(exist_ok=True)
        drawing=draw(candidate,figs)
        old.dump(OUT/'evidence.json',dict(valid=replay['valid'] and cert['status']=='all_original_rows_satisfied',
                 phase='feasible_schedule',start=data['cmax'],upper=physical['cmax'],lower=lower,gap=gap,
                 gate=gap<=TARGET,secondary_started=gap<=TARGET,physical=physical,idle=engine.measure(times),
                 replay=replay,original_rows=cert['original_rows'],figure=drawing,windows=len(state['records']),
                 schedule_sha256=old.digest(OUT/'result.json'),source_sha256=spec['input'],resources=first.sample(),
                 elapsed_this_invocation=time.monotonic()-start))
        print(f"D75 3/3, failed 0, ETA 0 | [{lower},{physical['cmax']}] gap {100*gap:.4f}%",flush=True)


if __name__=='__main__':
    execute()
