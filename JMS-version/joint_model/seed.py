"""Deterministic feasible construction, used only as an initial solution.

Pairing/chamber/order are released in the main solve. A serial seed is deliberately
simple enough to verify independently; its construction cost is recorded.
"""
from collections import defaultdict
from dataclasses import asdict
from model import products_from_load_ports
from validate import validate

def construct(cfg, template=None):
    products=products_from_load_ports(cfg.load_ports);byid={w.identifier:w for w in products}
    available=set(f'D{i+1}' for i in range(cfg.dummy_count));now=0.;robotend=defaultdict(dict);upper_free=lower_free=0.;events=[];jobs=[];pairs=[];cycles=[]
    chamber=cfg.chambers[0];loc=f'CH{chamber}';active_jobs={};pair_members={};loaded=set()
    def event(name,kind,robot,location,duration=None,**meta):
        nonlocal now
        if robot:
            # The model and replay checker impose travel on every ordered
            # event pair, including nonadjacent events. Keep the latest end
            # at each location: an intervening origin_put does not remove
            # an earlier LL-to-origin_pick minimum interval.
            for prev,end in robotend[robot].items():
                move=0 if prev==location or {prev,location}<={'U','L'} else cfg.atr_travel if robot=='ATR' else cfg.vtr_travel
                if robot=='ATR' and prev in ('U','L') and (location.startswith('LP') or location=='AS') and kind=='origin_pick':move=cfg.atr_empty_ll_to_lp
                now=max(now,end+move)
        d=duration if duration is not None else cfg.atr_handling if robot=='ATR' else cfg.handling
        e=dict(name=name,kind=kind,robot=robot,start=now,end=now+d,location=location,**meta);events.append(e);now+=d
        if robot:robotend[robot][location]=now
        return e
    def newpair(mode,members):
        p=len(pairs);pairs.append(dict(id=p,members=list(members),mode=mode,chamber=chamber));pair_members[p]=members;return p
    def load(p):
        nonlocal now,upper_free
        pair=pairs[p]
        for r,w in enumerate(pair['members']):
            isproduct=w in byid
            if w is None:
                if not available:raise ValueError('Seed lacks available dummy; increase inventory or use a different construction')
                w=sorted(available,key=lambda t:int(t[1:]))[0];available.remove(w);pair['members'][r]=w
            if not isproduct and w in available:available.remove(w)
            name=w if isproduct else f'aux_{p}_{r}';origin=f'LP{byid[w].load_port}' if isproduct else 'AS' if cfg.source=='single' else 'VS'
            j=dict(name=name,identity=w,product=isproduct,pair=p,origin=origin)
            def ev(k,rob,l):return event(name+'_'+k,k,rob,l,job=name)
            if origin!='VS':
                first=ev('origin_pick','ATR',origin)
                if isproduct or cfg.dummy_alignment=='legacy_align_all':
                    ap=ev('al_put','ATR','AL');now=max(now,ap['end']+cfg.alignment);ev('al_pick','ATR','AL')
                now=max(now,upper_free);up=ev('upper_put','ATR','U');now=max(now,up['end']+cfg.pump);pick=ev('source_pick','VTR','U');upper_free=pick['end']+cfg.upper_reset
            else:first=ev('source_pick','VTR','VS')
            j['loan_start']=first['start'];jobs.append(j);active_jobs[name]=j
        e=event(f'load_{p}','pair_load','VTR',loc,pair=p)
        for j in jobs:
            if j['pair']==p:j.update(load_start=e['start'],load_end=e['end'])
        loaded.add(p)
    def unload(p):
        nonlocal now,lower_free
        e=event(f'unload_{p}','pair_unload','VTR',loc,pair=p)
        for j in jobs:
            if j['pair']!=p:continue
            j.update(unload_start=e['start'],unload_end=e['end']);name=j['name']
            def ev(k,rob,l):return event(name+'_'+k,k,rob,l,job=name)
            if j['origin']!='VS':
                now=max(now,lower_free);put=ev('destination_put','VTR','L');now=max(now,put['end']+cfg.vent);pick=ev('lower_pick','ATR','L');lower_free=pick['end']+cfg.lower_reset;last=ev('origin_put','ATR',j['origin'])
            else:last=ev('destination_put','VTR','VS')
            j['loan_end']=last['end']
            if not j['product']:available.add(j['identity'])
        loaded.remove(p)
    def rotate(q,after=False):event(f'rot_{"after" if after else "before"}_{chamber}_{q}','rotate',None,loc,cfg.rotation,chamber=chamber,cycle=q)
    counter=0
    def exposure(mode,back,front):
        nonlocal now,counter
        q=sum(c['chamber']==chamber for c in cycles);duration={'4x1':cfg.full_time,'2x2':cfg.mix_time,'clean':cfg.cleaning_time}[mode]
        counter=0 if mode=='clean' else counter+1
        cycles.append(dict(chamber=chamber,index=q,mode=mode,start=now,end=now+duration,counter=counter,pairs=[back,front],front=front));now+=duration
    def batch(mode,member_pairs):
        back=newpair(mode,member_pairs[0]);front=newpair(mode,member_pairs[1]);q=len(cycles)
        load(back);rotate(q);load(front);exposure(mode,back,front);unload(front);rotate(q,True);unload(back)
    def clean():batch('clean',[[None,None],[None,None]])
    if template is not None:
        import copy
        pairs=copy.deepcopy(sorted(template['pairs'],key=lambda p:p['id']))
        if [p['id'] for p in pairs]!=list(range(len(pairs))):raise ValueError('Template pair IDs must be contiguous')
        for chamber in cfg.chambers:
            loc=f'CH{chamber}';counter=0
            cs=sorted((c for c in template['cycles'] if c['chamber']==chamber),key=lambda c:c['index'])
            previous=None
            for q,c in enumerate(cs):
                front=c['front'];back=next(p for p in c['pairs'] if p!=front)
                carry=set(c['pairs'])&set(previous['pairs']) if previous else set()
                if carry:
                    if carry!={back} or back!=previous['front']:raise ValueError('Invalid retained pair in template')
                    rotate(q);unload(next(p for p in previous['pairs'] if p!=back));load(front)
                else:load(back);rotate(q);load(front)
                exposure(c['mode'],back,front)
                retained=set(c['pairs'])&set(cs[q+1]['pairs']) if q+1<len(cs) else set()
                if not retained:unload(front);rotate(q,True);unload(back)
                previous=c
    else:
        groups={k:[] for k in ('4x1','2x2')}
        for mode in groups:
            ws=[w.identifier for w in products if w.mode==mode]
            groups[mode]=[ws[i:i+2]+[None]*(2-len(ws[i:i+2])) for i in range(0,len(ws),2)]
        fs=groups['4x1']
        for i in range(0,len(fs),2):
            batch('4x1',[fs[i],fs[i+1] if i+1<len(fs) else [None,None]])
            if counter==cfg.cleaning_interval:clean()
        remaining=list(groups['2x2'])
        while remaining:
            if counter==cfg.cleaning_interval-1:clean()
            count=min(len(remaining),cfg.cleaning_interval-counter-1);segment=remaining[:count];remaining=remaining[count:]
            oldback=newpair('2x2',[None,None]);oldfront=newpair('2x2',segment[0]);q=len(cycles)
            load(oldback);rotate(q);load(oldfront);exposure('2x2',oldback,oldfront)
            for members in segment[1:]+[[None,None]]:
                q=len(cycles);rotate(q);unload(oldback);incoming=newpair('2x2',members);load(incoming);exposure('2x2',oldfront,incoming);oldback,oldfront=oldfront,incoming
            unload(oldfront);rotate(len(cycles)-1,True);unload(oldback)
            if counter==cfg.cleaning_interval:clean()
    result=dict(schema=1,config=asdict(cfg),solutions=1,status='constructed',events=events,jobs=jobs,pairs=pairs,cycles=cycles,cmax=max(j['loan_end'] for j in jobs if j['product']),model_scope='joint_event_model',cleaning_policy='optional_before_threshold')
    if cfg.vtr_hand_policy=='clean_dirty':
        from grippers import attach_hands
        if not attach_hands(result):raise ValueError('Seed cannot assign two clean and two dirty VTR hands')
    result['validation']=validate(result)
    if not result['validation']['valid']:raise ValueError(result['validation']['errors'])
    if max(e['end'] for e in events)>cfg.horizon:raise ValueError('Seed exceeds time horizon')
    return result

def constrain_seed(x,data):
    """Temporary constraints for completing helper variables of the seed."""
    m=x.model;fix=[];pp={p['id']:p for p in data['pairs']};cc={(c['chamber'],c['index']):c for c in data['cycles']};ee={e['name']:e for e in data['events']}
    if max(pp,default=-1)>=x.P or max((q for c,q in cc),default=-1)>=x.Q:raise ValueError('Seed exceeds configured candidate bounds')
    def eq(var,value):
        fix.append((var,var.getLbOriginal(),var.getUbOriginal()));m.chgVarLb(var,value);m.chgVarUb(var,value)
    for p in range(x.P):
        chosen=pp.get(p);eq(x.pair.active[p],int(chosen is not None))
        for r in (0,1):
            w=chosen['members'][r] if chosen else None
            for prod in x.products:eq(x.pair.member[prod.identifier,p,r],int(w==prod.identifier))
            for t in (f'D{i+1}' for i in range(x.cfg.dummy_count)):eq(x.pair.dummy_identity[t,p,r],int(w==t))
        for mode in ('4x1','2x2','clean'):eq(x.pair.mode[p,mode],int(bool(chosen and chosen['mode']==mode)))
        for c in x.cfg.chambers:eq(x.pair.chamber[p,c],int(bool(chosen and chosen['chamber']==c)))
    for (c,q),used in x.cy.used.items():
        chosen=cc.get((c,q));eq(used,int(chosen is not None));eq(x.cy.start[c,q],chosen['start'] if chosen else 0);eq(x.cy.end[c,q],chosen['end'] if chosen else 0)
        for p in range(x.P):eq(x.cy.occupancy[p,c,q],int(bool(chosen and p in chosen['pairs'])));eq(x.front[p,c,q],int(bool(chosen and p==chosen['front'])))
        for mode in ('4x1','2x2','clean'):eq(x.cy.kind[c,q,mode],int(bool(chosen and chosen['mode']==mode)))
    for e in x.events:
        chosen=ee.get(e['name']);eq(e['s'],chosen['start'] if chosen else 0);eq(e['e'],chosen['end'] if chosen else 0)
    eq(x.cmax,data['cmax'])
    return fix
