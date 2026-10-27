"""Objective-preserving completion bound for the dual-source model.

After product-return U, only VS dummy handling, chamber rotation and at most
one terminal cleaning per chamber can remain. Compress that suffix, keeping
the prefix and all discrete choices. See terminal_cleanup_proof.md.
"""
import math


def cleanup_certificate(cfg, upper, capacity):
    if cfg.source != 'dual':
        raise ValueError('Cleanup theorem currently covers dual-source routes only')
    p=capacity['pairs'];q=capacity['cycles_per_chamber'];m=len(cfg.chambers)
    # 2P pair load/unload + 4P VS picks/puts + 2mQ rotations.
    events=6*p+2*m*q
    # Start/end nodes of those events, plus two nodes per terminal cleaning.
    vertices=2*events+2*m
    step=max(cfg.handling,cfg.rotation,cfg.vtr_travel)
    bound=math.ceil(upper+max(cfg.upper_reset,cfg.lower_reset)
                    +vertices*step+m*cfg.cleaning_time)
    if min(cfg.module_residency,cfg.robot_residency)<bound:
        raise ValueError('Cannot discard residency upper edges within this completion bound')
    horizon=min(cfg.horizon,bound)
    return dict(theorem='dual_terminal_cleanup_normal_form_v1',upper=upper,
                original_horizon=cfg.horizon,normal_form_horizon=horizon,
                remaining_event_bound=events,time_vertex_bound=vertices,
                max_short_edge=step,terminal_cleaning_allowance=m,
                scope='Every feasible sublevel schedule has a completion with identical product times in this horizon; not every original suffix timestamp is retained')
