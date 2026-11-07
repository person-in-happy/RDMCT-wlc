"""Complete a fixed physical seed in its active submodel, then check the full LP.

Only preparation and fixed-skeleton SPBS use the active submodel. The formal
search retains all original candidates. Every lifted assignment is checked
against the complete untransformed model and independently replayed.
"""
from dataclasses import replace
from model import Integrated
from seed import constrain_seed,release_fixed
from validate import validate
from joint_algorithms import improve_skeleton


def lift(full, small_values):
    values={}
    for var in full.model.getVars(transformed=False):
        # The first unused cycle still needs an empty-boundary witness for the
        # previous cycle's last unloading. H satisfies that existential bound.
        default=full.H if var.name.startswith(('empty_boundary_','exchange_boundary_')) else 0
        values[var.name]=small_values.get(var.name,default)
    m=full.model;sol=m.createSol()
    for var in m.getVars(transformed=False):m.setSolVal(sol,var,values[var.name])
    try:
        if not m.checkSol(sol,printreason=True,completely=True,original=True):
            raise RuntimeError('Lifted reference rejected by complete original compact model')
        physical=validate(full.result(solution=sol))
        if not physical['valid']:raise RuntimeError('Lifted reference failed independent physical replay')
    finally:m.freeSol(sol)
    return values


def complete_reference(full, schedule, memory_mb, spbs_budget=0):
    verdict=validate(schedule)
    if not verdict['valid']:raise ValueError('Invalid physical reference')
    pairs=max(p['id'] for p in schedule['pairs'])+1
    cycles=max(c['index'] for c in schedule['cycles'])+1
    if pairs>full.P or cycles>full.Q:raise ValueError('Reference exceeds complete candidate capacity')
    small=Integrated(replace(full.cfg,max_pairs=pairs,max_cycles=cycles));m=small.model
    try:
        fixed=constrain_seed(small,schedule)
        m.setObjective(0);m.setRealParam('limits/time',60)
        m.setRealParam('limits/memory',memory_mb);m.optimize()
        if not m.getNSols():raise RuntimeError('Active reference completion failed: '+str(m.getStatus()))
        if not m.checkSol(m.getBestSol(),completely=True,original=True):
            raise RuntimeError('Active reference failed original constraints')
        serial={v.name:m.getSolVal(m.getBestSol(),v) for v in m.getVars(transformed=False)}
        m.freeTransform();release_fixed(m,fixed)
        initial=lift(full,serial)
        # All SPBS levels keep jp membership/activation and jc kind fixed.
        # Omitted pairs and cycles therefore remain inactive at every level.
        improved,levels=improve_skeleton(small,serial,spbs_budget)
        common=initial if not levels else lift(full,improved)
        return initial,common,levels,dict(active_pairs=pairs,active_cycles_per_chamber=cycles,
            full_pairs=full.P,full_cycles_per_chamber=full.Q,
            scope='Only fixed-reference completion and SPBS; formal search is unrestricted',
            complete_model_check=True,independent_physical_check=True)
    finally:m.freeProb()
