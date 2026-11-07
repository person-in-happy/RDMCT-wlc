"""Pjob inventory choices. No variable is indexed by a physical product ID."""
from dataclasses import dataclass
from scip_imports import scip


@dataclass
class PairingDecisions:
    active: dict
    member: dict
    dummy: dict
    dummy_identity: dict
    mode: dict
    chamber: dict
    product: dict


def add_pjob_pairing(model,groups,dummy_ids,chambers,max_pairs,product_pair_bound):
    B=lambda name:model.addVar(vtype='B',name=name)
    P=range(max_pairs);R=(0,1);N=product_pair_bound
    active={p:B(f'jp_active_{p}') for p in P}
    # At most N pairs contain product. Such pairs can be labelled first, and
    # their first member can be product, without fixing any physical order.
    product={(p,r):(active[p] if r==0 else B(f'pj_product_{p}_{r}')) if p<N else 0 for p in P for r in R}
    x={(g.identifier,p,r):B(f'pj_x_{g.identifier}_{p}_{r}') for g in groups for p in range(min(N,max_pairs)) for r in R}
    dummy={(p,r):active[p]-product[p,r] if p<N and r==1 else 0 if p<N else active[p] for p in P for r in R}
    identity={(t,p,r):B(f'jp_identity_{t}_{p}_{r}') if not(p<N and r==0) else 0 for t in dummy_ids for p in P for r in R}
    enabled={g.mode for g in groups}|{'clean'}
    mode={(p,k):B(f'jp_mode_{p}_{k}') if k in enabled and not(p<N and k=='clean') else 0 for p in P for k in ('4x1','2x2','clean')}
    chamber={(p,c):B(f'jp_chamber_{p}_{c}') for p in P for c in chambers}
    for g in groups:
        model.addCons(scip.quicksum(x[g.identifier,p,r] for p in range(min(N,max_pairs)) for r in R)==g.count)
    for p in P:
        if p<N:model.addCons(product[p,1]<=active[p])
        for r in R:
            if p<N:model.addCons(scip.quicksum(x[g.identifier,p,r] for g in groups)==product[p,r])
            if not(p<N and r==0):model.addCons(scip.quicksum(identity[t,p,r] for t in dummy_ids)==dummy[p,r])
        for t in dummy_ids:model.addCons(identity[t,p,0]+identity[t,p,1]<=1)
        model.addCons(scip.quicksum(mode[p,k] for k in ('4x1','2x2','clean'))==active[p])
        model.addCons(scip.quicksum(chamber[p,c] for c in chambers)==active[p])
        if p<N:
            for g in groups:
                for r in R:
                    model.addCons(x[g.identifier,p,r]<=mode[p,g.mode])
                    model.addCons(x[g.identifier,p,r]<=scip.quicksum(chamber[p,c] for c in g.chambers))
        if p+1<max_pairs and p+1!=N:
            model.addCons(active[p+1]<=active[p])
    return PairingDecisions(active,x,dummy,identity,mode,chamber,product)
