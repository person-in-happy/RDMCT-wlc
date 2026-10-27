"""Valid workload bounds including intermediate cleaning and 2x2 chains."""
import math


def double_exposure_work(k,h,duration,cleaning):
    """k product pairs need at least ceil(k/(H-1)) nonempty blocks."""
    if k==0:return (0,0,0)
    blocks=math.ceil(k/(h-1))
    productive=k+blocks
    nonterminal=blocks-1
    return productive,nonterminal,productive*duration+nonterminal*cleaning


def add_cycle_work_bounds(x,upper,certificate):
    m=x.model;cfg=x.cfg;lead=certificate['route_lead'];tail=certificate['route_tail']
    pure2=all(w.mode=='2x2' for w in x.products)
    result=dict(theorem='cycle_work_and_double_exposure_blocks_v1',pure_2x2=pure2)
    if pure2:
        from pure2_block_certificate import block_certificate
        n=len(x.products);kcrit=math.ceil(math.ceil(n/2)/len(cfg.chambers))
        p,c,work=double_exposure_work(kcrit,cfg.cleaning_interval,cfg.mix_time,cfg.cleaning_time)
        lower=lead+tail+work
        m.addCons(x.cmax>=lower,name='largest_chamber_2x2_block_work')
        feasible=[k for k in range(1,n+1) if double_exposure_work(k,cfg.cleaning_interval,cfg.mix_time,cfg.cleaning_time)[2]<=upper-lead-tail+1e-6]
        maxk=max(feasible)
        blocks_proof=block_certificate(n,len(cfg.chambers),cfg.cleaning_interval,
             cfg.mix_time,cfg.cleaning_time,upper-lead-tail,certificate['max_productive_per_chamber'])
        result['block_count_certificate']=blocks_proof
        m.addCons(sum(x.cy.product_pair.values())>=math.ceil(n/2))
        m.addCons(sum(x.cy.product_pair.values())<=len(cfg.chambers)*maxk)
        m.addCons(sum(x.pair.active.values())==2*sum(x.cy.used.values())-sum(x.cy.product_pair.values()))
        result.update(max_product_pairs_per_chamber=maxk,global_work_lower_bound=lower,
                      largest_chamber_min_pairs=kcrit,largest_chamber_min_productive=p,
                      largest_chamber_min_nonterminal_cleanings=c)
        variables={v.name:v for v in m.getVars(transformed=False)}
    for ch in cfg.chambers:
        terminal=[]
        for q in range(x.Q):
            following=x.cy.used[ch,q+1] if q+1<x.Q else 0
            terminal.append(x.and_(x.cy.kind[ch,q,'clean'],1-following,f'bound_terminal_clean_{ch}_{q}'))
        intermediate=sum(x.cy.kind[ch,q,'clean'] for q in range(x.Q))-sum(terminal)
        prod=sum(x.cy.kind[ch,q,'4x1']+x.cy.kind[ch,q,'2x2'] for q in range(x.Q))
        work=sum(cfg.full_time*x.cy.kind[ch,q,'4x1']+cfg.mix_time*x.cy.kind[ch,q,'2x2'] for q in range(x.Q))+cfg.cleaning_time*intermediate
        blocks=intermediate+x.cy.used[ch,0]
        m.addCons(x.cmax>=lead+tail+work,name=f'work_including_intermediate_clean_CH{ch}')
        m.addCons(prod>=blocks)
        m.addCons(prod<=cfg.cleaning_interval*blocks)
        if pure2:
            pairs=sum(variables[f'jc_pf_{p}_{ch}_{q}'] for p in range(x.P) for q in range(x.Q))
            m.addCons(pairs<=maxk)
            m.addCons(pairs>=blocks_proof['min_pairs'])
            m.addCons(pairs>=blocks)
            m.addCons(pairs<=(cfg.cleaning_interval-1)*blocks)
            m.addCons(prod>=pairs+blocks)
            if blocks_proof['min_pairs']:
                m.addCons(intermediate>=blocks_proof['min_nonterminal_cleanings'])
                m.addCons(intermediate<=blocks_proof['max_nonterminal_cleanings'])
                m.addCons(prod>=blocks_proof['min_productive'])
                m.addCons(prod<=blocks_proof['max_productive'])
            forced=blocks_proof['forced_cycle_modes']
            if forced:
                if len(forced)>x.Q:raise ValueError('Capacity contradicts derived necessary block counts')
                for q in range(x.Q):
                    if q<len(forced):m.addCons(x.cy.kind[ch,q,forced[q]]==1)
                    else:m.addCons(x.cy.used[ch,q]==0)
    return result
