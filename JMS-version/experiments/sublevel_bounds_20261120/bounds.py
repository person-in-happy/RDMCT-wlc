"""First-stage bounds for the two-chamber, product-return model.

The count relaxation deliberately omits transfer conflicts and chamber
eligibility. Every physical schedule under the incumbent cap projects into
it. Terminal cleaning is counted separately from the production window.
"""
from functools import lru_cache
from math import ceil, floor


def route_times(cfg):
    a, t = cfg.atr_handling, cfg.atr_travel
    v, s = cfg.handling, cfg.vtr_travel
    lead = 4*a + 2*t + cfg.alignment + cfg.pump + 2*v + s
    tail = 2*v + s + cfg.vent + 2*a + t
    return lead, tail


def lock_bound(cfg):
    counts = {mode: sum(port.get(mode, 0) for port in cfg.load_ports.values())
              for mode in ('4x1', '2x2')}
    exposure = min(duration for mode, duration in
                   [('4x1', cfg.full_time), ('2x2', 2*cfg.mix_time)] if counts[mode])
    a, t, v = cfg.atr_handling, cfg.atr_travel, cfg.handling
    align = 2*a + cfg.alignment
    slot = a + cfg.pump + v + cfg.upper_reset
    entry = []
    for k in range(1, sum(counts.values()) + 1):
        earliest = a + 2*t + k*align
        if k > 2:
            earliest = max(earliest, entry[-2] + slot)
        entry.append(earliest)
    _, tail = route_times(cfg)
    remaining = a + cfg.pump + 2*v + cfg.vtr_travel + exposure + tail
    return {'entries': entry, 'slot_duration': slot, 'remaining': remaining,
            'lower': entry[-1] + remaining}


def capacity(cfg, upper):
    """Upper bounds on active cycle indices and auxiliary-only pair labels."""
    if len(cfg.chambers) != 2 or cfg.max_pairs or cfg.max_cycles:
        raise ValueError('Expected two chambers and the unrestricted source model')
    nf, nm = (sum(p.get(k, 0) for p in cfg.load_ports.values()) for k in ('4x1','2x2'))
    lead, tail = route_times(cfg)
    window = upper - lead - tail

    @lru_cache(maxsize=None)
    def chamber(f, m):
        if not (f or m):
            return (0, 0, 0)
        limits = None
        # One full cycle holds at most four full products. Every 2x2 product
        # pair has its own first exposure, followed by a second exposure.
        for full in range(ceil(f/4), f+1):
            for mixed in range(ceil(m/2)+1 if m else 0, 2*m+1):
                prod = full + mixed
                residual = window - full*cfg.full_time - mixed*cfg.mix_time
                internal = min(prod-1, floor((residual+1e-5)/cfg.cleaning_time))
                if internal < (prod-1)//cfg.cleaning_interval:
                    continue
                # One further terminal cleaning per active chamber is allowed.
                candidate = (prod+internal+1, prod+2*(internal+1), internal)
                limits = candidate if limits is None else tuple(map(max, zip(limits, candidate)))
        return limits

    splits = []
    cycles = auxiliaries = intermediate = 0
    for f in range(nf+1):
        for m in range(nm+1):
            x, y = chamber(f,m), chamber(nf-f,nm-m)
            if x is None or y is None:
                continue
            splits.append((f,m))
            cycles = max(cycles, x[0], y[0])
            auxiliaries = max(auxiliaries, x[1]+y[1])
            intermediate = max(intermediate, x[2], y[2])
    if not splits:
        raise ValueError('Validated incumbent conflicts with the resource relaxation')
    original_prod = nf+2*nm
    separated = bool(nf and nm) and set(splits) == {(nf,0),(0,nm)}
    return dict(window=window, lead=lead, tail=tail, feasible_splits=len(splits),
                separated=separated, max_intermediate=intermediate,
                pairs=nf+nm+min(3*original_prod, auxiliaries),
                cycles=min(2*original_prod, cycles))


def strengthen(x, plan, start, upper):
    m, cy, cfg = x.model, x.cy, x.cfg
    m.addCons(x.cmax >= lock_bound(cfg)['lower'], name='aligner_and_inlet_slots')
    m.addCons(x.cmax <= upper+1e-6, name='validated_product_return_cap')
    for c in cfg.chambers:
        for q in range(x.Q):
            prod = cy.kind[c,q,'4x1'] + cy.kind[c,q,'2x2']
            clean = cy.kind[c,q,'clean']
            m.addCons(cy.start[c,q] >= plan['lead']*prod)
            m.addCons(cy.end[c,q] <= (upper-plan['tail']+1e-6)*prod + x.H*clean)
            if plan['max_intermediate'] == 0 and q+1 < x.Q:
                m.addCons(clean + cy.used[c,q+1] <= 1)
    if not plan['separated']:
        return
    # Both orientations are physically equivalent only with identical
    # eligibility and the common chamber durations/travel of this backend.
    if any(set(group.chambers) != set(cfg.chambers) for group in x.groups):
        return
    modes = {row['chamber']: row['mode'] for row in start['cycles'] if row['mode'] != 'clean'}
    if set(modes.values()) != {'4x1','2x2'} or any(
            row['mode'] not in ('clean', modes[row['chamber']]) for row in start['cycles']):
        raise ValueError('Input does not realize the certified separation')
    for c, mode in modes.items():
        other = '2x2' if mode == '4x1' else '4x1'
        for q in range(x.Q):
            m.addCons(cy.kind[c,q,other] == 0)
        m.addCons(cy.kind[c,0,mode] == 1)
