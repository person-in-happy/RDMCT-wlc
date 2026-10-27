"""Binary pairing and chamber-assignment block for the revised scheduling model.

This block is deliberately independent of the legacy fixed-layout generator.
It must be combined with event timing, cleaning, and resource constraints;
a feasible solution of this block alone is not a feasible equipment schedule.
"""
from dataclasses import dataclass
from itertools import combinations
from scip_imports import scip


@dataclass(frozen=True)
class ProductWafer:
    identifier: str
    load_port: int
    mode: str


@dataclass
class PairingDecisions:
    active: dict
    member: dict
    dummy: dict
    dummy_identity: dict
    mode: dict
    chamber: dict


def add_joint_pairing(model, products, dummy_ids, chambers, compatible_chambers,
                      *, allow_cross_lp, max_pairs=None):
    """Add product/dummy membership and chamber choice, all as binary decisions.

    Products occur exactly once. Each active pair has two member positions.
    Dummy identity can recur in different pairs: the scheduling layer MUST
    impose nonoverlap from storage pickup through storage return on each
    physical dummy. No chamber or product pairing is prescribed here.
    max_pairs is a caller-supplied safe bound including dummy-only support pairs.
    Product recipes are input attributes, not optimization choices.
    """
    products = tuple(products)
    dummy_ids = tuple(dummy_ids)
    chambers = tuple(chambers)
    if len({w.identifier for w in products}) != len(products):
        raise ValueError('Product identifiers must be unique')
    if any(w.load_port not in (1, 2, 3, 4) for w in products):
        raise ValueError('Each product must originate at LP1, LP2, LP3, or LP4')
    if len(set(dummy_ids)) != len(dummy_ids) or len(set(chambers)) != len(chambers):
        raise ValueError('Dummy and chamber identifiers must be unique')
    modes = tuple(compatible_chambers)
    if any(w.mode not in modes for w in products):
        raise ValueError('Every product recipe requires chamber eligibility data')
    if any(not set(cs) <= set(chambers) for cs in compatible_chambers.values()):
        raise ValueError('Unknown compatible chamber')
    if max_pairs is None:
        max_pairs = len(products)
    if not isinstance(max_pairs, int) or max_pairs < 0:
        raise ValueError('max_pairs must be a nonnegative integer')
    pairs, positions = range(max_pairs), (0, 1)
    def binary(name):
        return model.addVar(vtype='B', name=name)
    active = {p: binary(f'jp_active_{p}') for p in pairs}
    member = {(w.identifier,p,r): binary(f'jp_member_{w.identifier}_{p}_{r}')
              for w in products for p in pairs for r in positions}
    dummy = {(p,r): binary(f'jp_dummy_{p}_{r}') for p in pairs for r in positions}
    identity = {(t,p,r): binary(f'jp_identity_{t}_{p}_{r}')
                for t in dummy_ids for p in pairs for r in positions}
    mode = {(p,m): binary(f'jp_mode_{p}_{m}') for p in pairs for m in modes}
    chamber = {(p,c): binary(f'jp_chamber_{p}_{c}') for p in pairs for c in chambers}
    for w in products:
        model.addCons(scip.quicksum(member[w.identifier,p,r] for p in pairs for r in positions)==1)
    for p in pairs:
        for r in positions:
            model.addCons(scip.quicksum(member[w.identifier,p,r] for w in products)+dummy[p,r]==active[p])
            model.addCons(scip.quicksum(identity[t,p,r] for t in dummy_ids)==dummy[p,r])
        for t in dummy_ids:
            model.addCons(identity[t,p,0]+identity[t,p,1]<=1)
        model.addCons(scip.quicksum(mode[p,m] for m in modes)==active[p])
        model.addCons(scip.quicksum(chamber[p,c] for c in chambers)==active[p])
        for w in products:
            for r in positions:
                model.addCons(member[w.identifier,p,r]<=mode[p,w.mode])
        for m in modes:
            for c in chambers:
                if c not in compatible_chambers[m]:
                    model.addCons(mode[p,m]+chamber[p,c]<=1)
        if not allow_cross_lp:
            for w,v in combinations(products,2):
                if w.load_port != v.load_port:
                    model.addCons(scip.quicksum(member[x.identifier,p,r]
                                  for x in (w,v) for r in positions)<=1)
    return PairingDecisions(active,member,dummy,identity,mode,chamber)


def products_from_load_ports(load_ports):
    """Expand explicit mode counts at LP1--LP4 into physical product identities."""
    expected={f'LP{i}' for i in range(1,5)}
    if set(load_ports)!=expected:
        raise ValueError('Specify all four load ports, including empty ones')
    products=[]
    for lp in range(1,5):
        counts=load_ports[f'LP{lp}']
        if set(counts)-{'4x1','2x2'}:
            raise ValueError('Unknown recipe mode')
        slot=0
        for mode in ('4x1','2x2'):
            count=counts.get(mode,0)
            if isinstance(count,bool) or not isinstance(count,int) or count<0:
                raise ValueError('Wafer counts must be nonnegative integers')
            for _ in range(count):
                slot+=1
                products.append(ProductWafer(f'LP{lp}_W{slot}',lp,mode))
    return tuple(products)


def add_pair_positions(model, decisions, positions):
    """Link free pair choices to candidate (mode, chamber, position) slots.

    Position is a hashable physical slot label, e.g. (batch, side) for 4x1.
    This adds no canonical assignment, fixed cleaning partition, or ordering.
    A downstream scheduling formulation must link selected positions to
    exposures, chamber capacity, cleaning and material transfer events.
    """
    positions=tuple(positions)
    if len(set(positions))!=len(positions):
        raise ValueError('Candidate positions must be unique')
    x={}
    for p in decisions.active:
        for m,c,k in positions:
            if (p,m) not in decisions.mode or (p,c) not in decisions.chamber:
                raise ValueError('Position uses an unknown mode or chamber')
            x[p,m,c,k]=model.addVar(vtype='B',name=f'jp_position_{p}_{m}_{c}_{k}')
            model.addCons(x[p,m,c,k]<=decisions.mode[p,m])
            model.addCons(x[p,m,c,k]<=decisions.chamber[p,c])
        model.addCons(scip.quicksum(x[p,m,c,k] for m,c,k in positions)==decisions.active[p])
    for m,c,k in positions:
        model.addCons(scip.quicksum(x[p,m,c,k] for p in decisions.active)<=1)
    return x


def add_dummy_reuse_timing(model, decisions, starts, ends, *, horizon):
    """Enforce nonoverlap of physical dummy loans, including all transport.

    starts/ends are bounded [0,horizon] scheduling expressions for each (p,r),
    from departure from vacuum storage through completed return. They must
    be linked to actual route events by the caller, not merely processing.
    """
    if horizon<=0:
        raise ValueError('A positive valid time horizon is required')
    jobs=set(decisions.dummy)
    if set(starts)!=jobs or set(ends)!=jobs:
        raise ValueError('Every dummy-use occurrence requires a complete loan interval')
    for j in jobs:
        model.addCons(ends[j]>=starts[j])
        model.addCons(starts[j]>=0);model.addCons(ends[j]<=horizon)
    orders={}
    tokens=sorted({t for t,_,_ in decisions.dummy_identity})
    for t in tokens:
        for i,j in combinations(sorted(jobs),2):
            a=decisions.dummy_identity[t,*i];b=decisions.dummy_identity[t,*j]
            y=model.addVar(vtype='B',name=f'jp_dummy_order_{t}_{i}_{j}')
            orders[t,i,j]=y
            model.addCons(y<=a);model.addCons(y<=b)
            model.addCons(ends[i]<=starts[j]+horizon*(3-a-b-y))
            model.addCons(ends[j]<=starts[i]+horizon*(2-a-b+y))
    return orders
