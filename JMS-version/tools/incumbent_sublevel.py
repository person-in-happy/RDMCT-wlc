"""Proven capacity bounds on schedules no worse than a feasible incumbent.

Every productive cycle contains a product and finishes by product-return Cmax.
Any cleaning other than the final cycle on its chamber precedes a productive
cycle and also finishes by Cmax. There is at most one final cleaning per
chamber. Thus Q <= floor(U/dmin)+1 on each chamber and sum Q <=
floor(m*U/dmin)+m. Each cycle has two occupied pairs; a product 2x2 pair
appears twice, every other pair once. P = 2*sum Q - number(product 2x2 pairs).
These are sublevel-set bounds, not arbitrary truncations. They leave the time
horizon and all physical constraints unchanged.
"""
import math


def product_route_margins(cfg):
    # Product pickup -> first exposure; last exposure -> original LP return.
    lead = 4*cfg.atr_handling+2*cfg.atr_travel+cfg.alignment+cfg.pump+2*cfg.handling+cfg.vtr_travel
    tail = 2*cfg.handling+cfg.vtr_travel+cfg.vent+2*cfg.atr_handling+cfg.atr_travel
    return lead, tail


def capacity_certificate(cfg, upper):
    if not math.isfinite(upper) or upper <= 0:
        raise ValueError('A positive finite validated upper bound is required')
    if cfg.max_pairs or cfg.max_cycles:
        raise ValueError('Source must use the unrestricted candidate capacity')
    nf = sum(v.get('4x1', 0) for v in cfg.load_ports.values())
    nl = sum(v.get('2x2', 0) for v in cfg.load_ports.values())
    n = nf+nl; productive = nf+2*nl; m = len(cfg.chambers)
    if not n or not m:
        raise ValueError('No products or chambers')
    durations = [cfg.cleaning_time]
    if nf:
        durations.append(cfg.full_time)
    if nl:
        durations.append(cfg.mix_time)
    dmin = min(durations)
    if dmin <= 0:
        raise ValueError('Positive durations required')
    # Outward slack protects floor operations from rounded input bounds.
    lead, tail = product_route_margins(cfg)
    window = upper-lead-tail
    proc_min = min(d for d, count in ((cfg.full_time,nf),(cfg.mix_time,nl)) if count)
    options = []
    for p in range(1,productive+1):
        # Before p productive cycles can finish, at least floor((p-1)/H)
        # intervening cleanings are necessary. A final cleaning is extra.
        for c in range((p-1)//cfg.cleaning_interval,p):
            if p*proc_min+c*cfg.cleaning_time <= window+1e-3:
                options.append((p,c))
    if not options:
        raise ValueError('Upper bound contradicts mandatory route/processing time')
    per_chamber = min(2*productive,max(p+c+1 for p,c in options))
    all_cycles = min(2*productive,m*per_chamber,math.floor(m*(window+1e-3)/dmin)+m)
    pairs = min(n+3*productive, 2*all_cycles-math.ceil(nl/2))
    return dict(schema=2, theorem='product_return_sublevel_capacity_v2', upper=upper,
                original_pairs=n+3*productive, original_cycles_per_chamber=2*productive,
                min_cycle_duration=dmin, terminal_cleaning_allowance=m,
                total_cycles=all_cycles, pairs=pairs, cycles_per_chamber=per_chamber,
                min_double_exposure_pairs=math.ceil(nl/2),
                route_lead=lead,route_tail=tail,production_window=window,
                max_productive_per_chamber=max(p for p,c in options),
                horizon_changed=False, scope='All feasible schedules with product-return Cmax <= upper')


def strengthen(x, upper, certificate):
    m = x.model; cfg = x.cfg
    m.addCons(x.cmax <= upper+1e-6, name='certified_incumbent_cutoff')
    m.addCons(sum(x.cy.used.values()) <= certificate['total_cycles'], name='certified_total_cycle_bound')
    min_processing = min(cfg.full_time if w.mode == '4x1' else 2*cfg.mix_time for w in x.products)
    # Last product to leave the single AL still has its complete remaining route.
    tail = (2*cfg.atr_travel + 3*cfg.atr_handling + cfg.pump + cfg.vent
            + 4*cfg.handling + 2*cfg.vtr_travel + min_processing)
    al_bound = cfg.atr_handling+cfg.atr_travel + len(x.products)*(2*cfg.atr_handling+cfg.alignment) + tail
    m.addCons(x.cmax >= al_bound, name='mandatory_AL_work_and_last_product_tail')
    for w in x.products:
        j = x.jobs[w.identifier]
        duration = cfg.full_time if w.mode == '4x1' else 2*cfg.mix_time
        m.addCons(j['unload_s'] >= j['load_e']+duration, name='product_total_exposure_'+w.identifier)
        m.addCons(j['load_s'] >= j['source_pick']['e']+cfg.vtr_travel)
        m.addCons(j['destination_put']['s'] >= j['unload_e']+cfg.vtr_travel)
        m.addCons(j['al_put']['s'] >= j['first']['e']+cfg.atr_travel)
        m.addCons(j['upper_put']['s'] >= j['al_pick']['e']+cfg.atr_travel)
        m.addCons(j['last']['s'] >= j['lower_pick']['e']+cfg.atr_travel)
        for e in x.events:
            if e.get('job') == w.identifier:
                m.chgVarUb(e['s'], min(e['s'].getUbOriginal(), upper+1e-6))
                m.chgVarUb(e['e'], min(e['e'].getUbOriginal(), upper+1e-6))
        for key in ('load_s', 'load_e', 'unload_s', 'unload_e'):
            m.chgVarUb(j[key], min(j[key].getUbOriginal(), upper+1e-6))
    for c in cfg.chambers:
        work = sum(cfg.full_time*x.cy.kind[c,q,'4x1'] + cfg.mix_time*x.cy.kind[c,q,'2x2'] for q in range(x.Q))
        m.addCons(x.cmax >= certificate['route_lead']+certificate['route_tail']+work, name=f'productive_work_CH{c}')
        m.addCons(sum(x.cy.kind[c,q,'4x1']+x.cy.kind[c,q,'2x2'] for q in range(x.Q))
                  <=certificate['max_productive_per_chamber'])
        for q in range(x.Q):
            productive_end=upper-certificate['route_tail']
            m.addCons(x.cy.end[c,q] <= (productive_end+1e-6)*x.cy.used[c,q]
                      + (x.H-productive_end)*x.cy.kind[c,q,'clean'])
            m.addCons(x.cy.start[c,q] >= certificate['route_lead']*(x.cy.kind[c,q,'4x1']+x.cy.kind[c,q,'2x2']))
            m.addCons(x.cy.start[c,q] >= q*certificate['min_cycle_duration']*x.cy.used[c,q])
    return dict(al_work_tail_bound=al_bound, cutoff=upper, time_horizon=cfg.horizon)
