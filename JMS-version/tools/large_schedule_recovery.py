"""Solver recovery settings and RAM/commit guards; no model restrictions."""
import math

import large_schedule_resources as telemetry
from large_schedule_resources import describe, pressure, snapshot


SCIP_PARAMETERS = {
    'misc/usesymmetry': 0,
    'propagating/probing/maxprerounds': 0,
    'propagating/probing/freq': -1,
}


def configure(model):
    """Disable automatic symmetry processing and the probing propagator."""
    for name, value in SCIP_PARAMETERS.items():
        model.setIntParam(name, value)
    return {name: model.getParam(name) for name in SCIP_PARAMETERS}


def policy(minimum=.05, disabled=False, min_commit_available_gib=8.):
    if not math.isfinite(min_commit_available_gib) or min_commit_available_gib < 0:
        raise ValueError('Commit reserve must be a finite nonnegative GiB value')
    result = telemetry.policy(minimum, disabled)
    reserve = 0. if disabled else min_commit_available_gib
    result.update(min_commit_available_gib=reserve,
                  memory_guard_enabled=not disabled and (minimum > 0 or reserve > 0))
    result['memory_policy'] = ('native_unlimited_with_ram_and_commit_reserve'
                              if result['memory_guard_enabled']
                              else 'native_unlimited_observe_only')
    return result


def stop_reason(settings, sample):
    if not settings.get('memory_guard_enabled', True):
        return None
    if sample['physical_available_fraction'] < settings['min_available_fraction']:
        return 'system_available_memory_guard'
    reserve = settings.get('min_commit_available_gib', 0) * 1024**3
    if reserve:
        if 'system_commit_available_bytes' not in sample:
            return 'system_commit_telemetry_unavailable'
        if sample['system_commit_available_bytes'] < reserve:
            return 'system_commit_memory_guard'
    return None


def should_stop(settings, sample):
    return stop_reason(settings, sample) is not None


def solver_stage(dest):
    """Report only phases evidenced by the log, without touching the solver."""
    if not (dest / 'build.json').exists():
        return 'building'
    log = dest / 'solver.log'
    if not log.exists():
        return 'initializing_solver'
    with log.open('rb') as stream:
        stream.seek(max(0, log.stat().st_size - 16384))
        tail = stream.read().decode('utf-8', errors='replace')
    if 'SCIP Status' in tail:
        return 'finalizing'
    if '| node' in tail or ' time |' in tail:
        return 'node_search'
    if 'symmetry computation started' in tail:
        return 'symmetry_detection'
    if 'presolving:' in tail or 'del vars' in tail or 'probing:' in tail:
        return 'presolving'
    return 'solver_running'
