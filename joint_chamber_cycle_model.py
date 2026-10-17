"""Free chamber-cycle and cleaning decisions for joint pairing.

This is the process/cleaning layer. Transport and physical chamber-side
handoff must be linked before its timing becomes an equipment schedule.
"""
from dataclasses import dataclass
from scip_imports import scip


@dataclass
class ChamberCycles:
    used: dict
    kind: dict
    occupancy: dict
    first: dict
    last: dict
    product_pair: dict
    start: dict
    end: dict
    counter: dict


def add_chamber_cycles(model, pairing, chambers, *, cycle_limit, cleaning_interval,
                       durations, horizon):
    if cycle_limit<1 or cleaning_interval<1 or horizon<=0:
        raise ValueError('Positive cycle limit, cleaning interval and horizon required')
    if set(durations)!={'4x1','2x2','clean'} or min(durations.values())<=0:
        raise ValueError('Specify positive durations for both recipes and cleaning')
    C=tuple(chambers);Q=range(cycle_limit);P=tuple(pairing.active);M=('4x1','2x2','clean')
    if any((p,m) not in pairing.mode for p in P for m in M):
        raise ValueError('Pairing block must include a dummy-only clean mode')
    def B(n):return model.addVar(vtype='B',name=n)
    used={(c,q):B(f'jc_used_{c}_{q}') for c in C for q in Q}
    kind={(c,q,m):B(f'jc_kind_{c}_{q}_{m}') for c in C for q in Q for m in M}
    occ={(p,c,q):B(f'jc_occ_{p}_{c}_{q}') for p in P for c in C for q in Q}
    first={(p,c,q):B(f'jc_first_{p}_{c}_{q}') for p in P for c in C for q in Q}
    last={(p,c,q):B(f'jc_last_{p}_{c}_{q}') for p in P for c in C for q in Q}
    has={p:B(f'jc_product_pair_{p}') for p in P}
    mixed={p:B(f'jc_mixed_product_{p}') for p in P}
    starts={(c,q):model.addVar(lb=0,ub=horizon,name=f'jc_start_{c}_{q}') for c in C for q in Q}
    ends={(c,q):model.addVar(lb=0,ub=horizon,name=f'jc_end_{c}_{q}') for c in C for q in Q}
    count={(c,q):model.addVar(vtype='I',lb=0,ub=cleaning_interval,name=f'jc_count_{c}_{q}') for c in C for q in Q}
    product_occ={};product_first={};product_last={}
    def AND(a,b,name):
        z=B(name);model.addCons(z<=a);model.addCons(z<=b);model.addCons(z>=a+b-1);return z
    for p in P:
        n=scip.quicksum(v for (w,j,r),v in pairing.member.items() if j==p)
        model.addCons(n>=has[p]);model.addCons(n<=2*has[p])
        model.addCons(pairing.mode[p,'clean']+has[p]<=1)
        model.addCons(mixed[p]<=has[p]);model.addCons(mixed[p]<=pairing.mode[p,'2x2'])
        model.addCons(mixed[p]>=has[p]+pairing.mode[p,'2x2']-1)
        model.addCons(scip.quicksum(occ[p,c,q] for c in C for q in Q)==pairing.active[p]+mixed[p])
        model.addCons(scip.quicksum(first[p,c,q] for c in C for q in Q)==pairing.active[p])
        model.addCons(scip.quicksum(last[p,c,q] for c in C for q in Q)==pairing.active[p])
        for c in C:
            for q in Q:
                o=occ[p,c,q];prev=occ[p,c,q-1] if q else 0;following=occ[p,c,q+1] if q+1<cycle_limit else 0
                model.addCons(o<=pairing.chamber[p,c])
                model.addCons(first[p,c,q]>=o-prev);model.addCons(first[p,c,q]<=o);model.addCons(first[p,c,q]<=1-prev)
                model.addCons(last[p,c,q]>=o-following);model.addCons(last[p,c,q]<=o);model.addCons(last[p,c,q]<=1-following)
                for m in M:model.addCons(o+pairing.mode[p,m]<=1+kind[c,q,m])
                product_occ[p,c,q]=AND(o,has[p],f'jc_po_{p}_{c}_{q}')
                product_first[p,c,q]=AND(first[p,c,q],mixed[p],f'jc_pf_{p}_{c}_{q}')
                product_last[p,c,q]=AND(last[p,c,q],mixed[p],f'jc_pl_{p}_{c}_{q}')
    H=cleaning_interval
    for c in C:
        for q in Q:
            u=used[c,q];k=kind[c,q,'clean'];proc=kind[c,q,'4x1']+kind[c,q,'2x2']
            model.addCons(scip.quicksum(kind[c,q,m] for m in M)==u)
            model.addCons(scip.quicksum(occ[p,c,q] for p in P)==2*u)
            model.addCons(scip.quicksum(product_occ[p,c,q] for p in P)>=proc)
            # A 2x2 cycle has at most one pair in its first exposure and one in its second.
            model.addCons(scip.quicksum(product_first[p,c,q] for p in P)<=1)
            model.addCons(scip.quicksum(product_last[p,c,q] for p in P)<=1)
            model.addCons(ends[c,q]==starts[c,q]+scip.quicksum(durations[m]*kind[c,q,m] for m in M))
            model.addCons(starts[c,q]<=horizon*u);model.addCons(ends[c,q]<=horizon*u)
            prev=count[c,q-1] if q else 0
            model.addCons(count[c,q]<=H*u);model.addCons(count[c,q]<=H*(1-k))
            model.addCons(count[c,q]>=prev+proc-(H+1)*(k+1-u))
            model.addCons(count[c,q]<=prev+proc+(H+1)*(k+1-u))
            # Cleaning is optional after any positive number of productive
            # cycles. The counter cap and successor constraints still force
            # cleaning at H, including after the final productive cycle.
            model.addCons(prev>=k)
            if q:
                model.addCons(u<=used[c,q-1])
                model.addCons(starts[c,q]>=ends[c,q-1]-horizon*(1-u))
                model.addCons(k+kind[c,q-1,'clean']<=1)
                model.addCons(prev<=H-1+H*k+H*(1-u))
            else:model.addCons(k==0)
            following=used[c,q+1] if q+1<cycle_limit else 0
            model.addCons(count[c,q]<=H-1+H*following)
    return ChamberCycles(used,kind,occ,first,last,has,starts,ends,count)
