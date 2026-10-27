"""Integrated event-based MILP for free PW pairing and source-dependent routes.

All times are seconds. Atomic robot handling, sequence-dependent travel,
physical gripper loans, LL reset and chamber orientation are represented.
No legacy fixed-layout generator is called.
"""
from dataclasses import dataclass, asdict, field
from itertools import combinations
from pathlib import Path
import sys, math
ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scip_imports import scip
from joint_pairing_model import add_joint_pairing,products_from_load_ports
from joint_chamber_cycle_model import add_chamber_cycles

@dataclass
class Config:
    load_ports: dict
    processing_groups: dict=field(default_factory=dict)
    source: str='dual'
    dummy_alignment: str='bypass_or_accompany'
    vtr_hand_policy: str='clean_dirty'
    dummy_count: int=8
    cleaning_interval: int=3
    full_time: float=180
    mix_time: float=90
    cleaning_time: float=500
    handling: float=1
    atr_handling: float=4
    atr_empty_ll_to_lp: float=6
    rotation: float=2
    atr_travel: float=3
    vtr_travel: float=2
    alignment: float=20
    pump: float=30
    vent: float=25
    upper_reset: float=30
    lower_reset: float=25
    module_residency: float=10000
    robot_residency: float=10000
    horizon: float=100000
    max_pairs: int=0
    max_cycles: int=0
    chambers: tuple=(1,2)

class Integrated:
    def __init__(self,cfg):
        self.cfg=cfg
        if cfg.vtr_hand_policy not in ('clean_dirty','legacy_unrestricted'):raise ValueError('Unknown VTR hand policy')
        if cfg.dummy_alignment not in ('bypass_or_accompany','legacy_align_all'):raise ValueError('Unknown dummy alignment policy')
        if cfg.source not in ('single','dual'):raise ValueError('source must be single or dual')
        if cfg.cleaning_interval<2:raise ValueError('H must be >=2 for the complete two-exposure recipe')
        if cfg.dummy_count<4:raise ValueError('At least four physical dummy wafers required for cleaning')
        for name in ('handling','rotation','full_time','mix_time','cleaning_time','horizon'):
            if getattr(cfg,name)<=0:raise ValueError(f'{name} must be positive')
        self.products=products_from_load_ports(cfg.load_ports)
        from recipes import validate_groups
        self.wafer_groups=validate_groups(cfg, self.products)
        if not self.products:raise ValueError('At least one product required')
        if cfg.dummy_count>10:raise ValueError('Auxiliary storage capacity is ten wafers')
        if any(sum(v.values())>25 for v in cfg.load_ports.values()):raise ValueError('Each LP holds at most 25 product wafers')
        nf=sum(w.mode=='4x1' for w in self.products);nl=len(self.products)-nf
        # Every productive cycle contains a product: at most nf+2*nl cycles.
        # At most one cleaning after each productive cycle; at most one
        # dummy-only support pair per productive cycle, two per cleaning.
        productive=nf+2*nl
        clean_bound=productive
        safe_pairs=len(self.products)+productive+2*clean_bound
        safe_cycles=productive+clean_bound
        self.P=cfg.max_pairs or safe_pairs;self.Q=cfg.max_cycles or safe_cycles
        self.bounded=self.P<safe_pairs or self.Q<safe_cycles
        self.safe_bounds={'pairs':safe_pairs,'cycles_per_chamber':safe_cycles}
        self.model=m=scip.Model('joint_complete_event_model');m.hideOutput()
        self.H=cfg.horizon;self.M=3*cfg.horizon+max(cfg.pump,cfg.vent,cfg.upper_reset,cfg.lower_reset)
        C=cfg.chambers
        self.pair=add_joint_pairing(m,self.products,tuple(f'D{i+1}' for i in range(cfg.dummy_count)),C,
            {k:C for k in ('4x1','2x2','clean')},allow_cross_lp=True,max_pairs=self.P)
        # Wafer positions and identical dummy labels are interchangeable.
        # These inequalities remove only label symmetry, never a physical route.
        for p in range(self.P):
            m.addCons(self.pair.dummy[p,0]<=self.pair.dummy[p,1])
            ids=[w.identifier for w in self.products]
            left=sum((i+1)*self.pair.member[w,p,0] for i,w in enumerate(ids))
            right=sum((i+1)*self.pair.member[w,p,1] for i,w in enumerate(ids))
            m.addCons(left<=right+(len(ids)+1)*self.pair.dummy[p,1])
        for t in range(2,cfg.dummy_count+1):
            earlier=[]
            for p in range(self.P):
                for r in (0,1):
                    m.addCons(self.pair.dummy_identity[f'D{t}',p,r]<=sum(earlier))
                    earlier.append(self.pair.dummy_identity[f'D{t-1}',p,r])
        self.cy=add_chamber_cycles(m,self.pair,C,cycle_limit=self.Q,cleaning_interval=cfg.cleaning_interval,
             durations={'4x1':cfg.full_time,'2x2':cfg.mix_time,'clean':cfg.cleaning_time},horizon=self.H,
             processing_groups=cfg.processing_groups)
        m.addCons(sum(self.cy.used.values())<=safe_cycles)
        m.addCons(sum(self.cy.kind[c,q,'clean'] for c in C for q in range(self.Q))<=clean_bound)
        self.events=[];self.robots={'ATR':[],'VTR':[]};self.intervals={};self.jobs={};self.vars={};self.counter=0
        self.front={};self.keep={};self.rot_before={};self.rot_after={};self.tail={}
        # Candidate-pair labels are interchangeable; prefix activation is safe.
        for p in range(self.P-1):m.addCons(self.pair.active[p+1]<=self.pair.active[p])
        self.load={p:self.event(f'load_{p}','pair_load','VTR',self.pair.active[p],
                 {f'CH{c}':self.pair.chamber[p,c] for c in C},pair=p) for p in range(self.P)}
        self.unload={p:self.event(f'unload_{p}','pair_unload','VTR',self.pair.active[p],
                 {f'CH{c}':self.pair.chamber[p,c] for c in C},pair=p) for p in range(self.P)}
        self.chambers()
        for w in self.products:
            member={p:self.pair.member[w.identifier,p,0]+self.pair.member[w.identifier,p,1] for p in range(self.P)}
            self.route(w.identifier,1,f'LP{w.load_port}',member,product=w.identifier)
        for p in range(self.P):
            for r in (0,1):
                self.route(f'aux_{p}_{r}',self.pair.dummy[p,r],
                    'AS' if cfg.source=='single' else 'VS',{p:1},dummy_position=(p,r))
        self.accompaniment()
        self.resources()
        # Dummy identity loans include all outbound and return handling.
        self.dummy_orders={}
        for t in (f'D{i+1}' for i in range(cfg.dummy_count)):
            loans=[]
            for p in range(self.P):
                for r in (0,1):
                    j=self.jobs[f'aux_{p}_{r}'];loans.append((f'{p}_{r}',j['first']['s'],j['last']['e'],self.pair.dummy_identity[t,p,r]))
            self.capacity('identity_'+t,loans,1)
        self.cmax=self.cont('Cmax')
        for w in self.products:m.addCons(self.cmax>=self.jobs[w.identifier]['last']['e'])
        self.primary_objective=self.cmax
        self.waits=[]
        for name,j in self.jobs.items():
            legs=[(j['load_s'],j['source_pick']['e'],cfg.vtr_travel),(j['destination_put']['s'],j['unload_e'],cfg.vtr_travel)]
            if j['origin']!='VS':
                by={e['kind']:e for e in self.events if e.get('job')==name}
                entry=[('origin_pick','al_put',cfg.atr_travel),('al_put','al_pick',cfg.alignment),('al_pick','upper_put',cfg.atr_travel)] if 'al_put' in by else [('origin_pick','upper_put',cfg.atr_travel)]
                for a,b,d in entry+[('upper_put','source_pick',cfg.pump),('destination_put','lower_pick',cfg.vent),('lower_pick','origin_put',cfg.atr_travel)]:
                    legs.append((by[b]['s'],by[a]['e'],d))
            for i,(end,start,duration) in enumerate(legs):
                wait=self.cont(f'wait_{name}_{i}');m.addCons(wait==end-start-duration*j['active']);self.waits.append(wait)
        self.max_wait=self.cont('max_wait')
        for w in self.waits:m.addCons(self.max_wait>=w)
        self.rhythm=[]
        for c in C:
            for q in range(2,self.Q):
                active=self.and_(self.keep[c,q],self.keep[c,q-1],f'rhythm_active_{c}_{q}')
                diff=self.cont(f'rhythm_{c}_{q}');delta=self.cy.start[c,q]-2*self.cy.start[c,q-1]+self.cy.start[c,q-2]
                self.ge(diff,delta,active);self.ge(diff,-delta,active);self.rhythm.append(diff)
        self.secondary_objective=sum(self.waits)+10*self.max_wait+25*sum(self.rhythm)
        m.setObjective(self.cmax,'minimize')
        self.original_dimensions={'variables':m.getNVars(),'constraints':m.getNConss()}
        self.original_dimensions['types']={t:sum(v.vtype()==t for v in m.getVars()) for t in ('BINARY','INTEGER','CONTINUOUS')}

    def bit(self,name):return self.model.addVar(vtype='B',name=name)
    def cont(self,name):return self.model.addVar(lb=0,ub=self.H,name=name)
    def and_(self,a,b,name):
        z=self.bit(name);self.model.addCons(z<=a);self.model.addCons(z<=b);self.model.addCons(z>=a+b-1);return z
    def ge(self,a,b,active=1):self.model.addCons(a>=b-self.M*(1-active))
    def eq(self,a,b,active=1):self.ge(a,b,active);self.ge(b,a,active)
    def event(self,name,kind,robot,active,location,duration=None,**meta):
        duration=(self.cfg.atr_handling if robot=='ATR' else self.cfg.handling) if duration is None else duration
        s=self.cont(name+'_s');e=self.cont(name+'_e')
        self.model.addCons(e==s+duration*active);self.model.addCons(s<=self.H*active);self.model.addCons(e<=self.H*active)
        obj=dict(name=name,kind=kind,robot=robot,active=active,location=location,s=s,e=e,**meta)
        self.events.append(obj)
        if robot:self.robots[robot].append(obj)
        return obj

    def chambers(self):
        m=self.model;cy=self.cy;cfg=self.cfg
        for c in cfg.chambers:
            for q in range(self.Q):
                carry=sum(cy.occupancy[p,c,q]-cy.first[p,c,q] for p in range(self.P))
                k=self.bit(f'carry_{c}_{q}');m.addCons(k==carry);self.keep[c,q]=k
                nextcarry=sum(cy.occupancy[p,c,q]-cy.last[p,c,q] for p in range(self.P))
                tail=self.bit(f'tail_{c}_{q}');m.addCons(tail==cy.used[c,q]-nextcarry);self.tail[c,q]=tail
                rb=self.event(f'rot_before_{c}_{q}','rotate',None,cy.used[c,q],{f'CH{c}':1},cfg.rotation,chamber=c,cycle=q)
                ra=self.event(f'rot_after_{c}_{q}','rotate',None,tail,{f'CH{c}':1},cfg.rotation,chamber=c,cycle=q)
                self.rot_before[c,q]=rb;self.rot_after[c,q]=ra
                self.ge(ra['s'],cy.end[c,q],tail)
                if q:self.ge(rb['s'],cy.end[c,q-1],k)
                fronts=[]
                for p in range(self.P):
                    occ=cy.occupancy[p,c,q];first=cy.first[p,c,q];last=cy.last[p,c,q]
                    f=self.bit(f'front_{p}_{c}_{q}');self.front[p,c,q]=f;fronts.append(f);m.addCons(f<=occ)
                    # A retained pair is at the back after rotating for the next cycle.
                    m.addCons(f<=first)
                    if q:m.addCons(self.front[p,c,q-1]>=occ-first)
                    # At a fresh 2x2 head the product pair loads last at the front.
                    m.addCons(f>=cy.product_pair[p]+cy.kind[c,q,'2x2']+occ-2-k)
                    self.ge(cy.start[c,q],self.load[p]['e'],occ)
                    self.ge(self.unload[p]['s'],cy.end[c,q],occ)
                    frontfirst=self.and_(f,first,f'ff_{p}_{c}_{q}')
                    backfirst=self.bit(f'bf_{p}_{c}_{q}');m.addCons(backfirst==first-frontfirst)
                    self.ge(rb['s'],self.load[p]['e'],backfirst)
                    self.ge(self.load[p]['s'],rb['e'],frontfirst)
                    self.eq(cy.start[c,q],self.load[p]['e'],frontfirst)
                    frontlast=self.and_(f,last,f'fl_{p}_{c}_{q}')
                    backlast=self.bit(f'bl_{p}_{c}_{q}');m.addCons(backlast==last-frontlast)
                    self.ge(ra['s'],self.unload[p]['e'],frontlast)
                    at_tail=self.and_(backlast,tail,f'bt_{p}_{c}_{q}')
                    self.ge(self.unload[p]['s'],ra['e'],at_tail)
                    if q+1<self.Q:
                        cont=self.bit(f'continuing_out_{p}_{c}_{q}');m.addCons(cont==backlast-at_tail)
                        # The old back pair is unloaded after the next rotation.
                        # Next rotation variables are created below; defer links.
                        self.vars['out',p,c,q]=cont
                m.addCons(sum(fronts)==cy.used[c,q])
        for c in cfg.chambers:
            for q in range(1,self.Q):
                empty=self.cont(f'empty_boundary_{c}_{q}')
                exchanged=self.cont(f'exchange_boundary_{c}_{q}')
                for p in range(self.P):
                    out=self.vars['out',p,c,q-1]
                    self.ge(self.unload[p]['s'],self.rot_before[c,q]['e'],out)
                    self.ge(exchanged,self.unload[p]['e'],out)
                    self.ge(empty,self.unload[p]['e'],self.cy.last[p,c,q-1])
                for j in range(self.P):
                    incoming=self.cy.first[j,c,q]
                    self.ge(self.load[j]['s'],exchanged,incoming)
                    self.model.addCons(self.load[j]['s']>=empty-self.M*(1-incoming+self.keep[c,q]))
        for p in range(self.P):
            self.ge(self.unload[p]['s'],self.load[p]['e'],self.pair.active[p])
            self.model.addCons(self.unload[p]['s']-self.load[p]['e']<=cfg.module_residency+self.M*(1-self.pair.active[p]))

    def route(self,name,active,origin,member,product=None,dummy_position=None):
        cfg=self.cfg;m=self.model
        atmospheric=origin!='VS'
        def ev(tag,robot,loc):return self.event(name+'_'+tag,tag,robot,active,{loc:1},job=name)
        j=dict(name=name,active=active,origin=origin,member=member,product=product,dummy_position=dummy_position)
        if atmospheric:
            ap=ev('origin_pick','ATR',origin);llput=ev('upper_put','ATR','U')
            align=product is not None or cfg.dummy_alignment=='legacy_align_all'
            if align:
                alput=ev('al_put','ATR','AL');alpick=ev('al_pick','ATR','AL')
                self.ge(alput['s'],ap['e'],active);self.ge(alpick['s'],alput['e']+cfg.alignment,active);self.ge(llput['s'],alpick['e'],active)
                self.add_interval('AL',name,alput['s'],alpick['e'],active)
                self.add_interval('ATR_hand',name+'_in1',ap['s'],alput['e'],active)
                self.add_interval('ATR_hand',name+'_in2',alpick['s'],llput['e'],active)
                m.addCons(alpick['s']-alput['e']<=cfg.module_residency+self.M*(1-active))
                j.update(al_put=alput,al_pick=alpick)
            else:
                # A dummy is never placed on AL. Its ATR gripper remains occupied
                # through an optional visit accompanying its product partner.
                self.ge(llput['s'],ap['e'],active)
                self.add_interval('ATR_hand',name+'_in',ap['s'],llput['e'],active)
            vp=ev('source_pick','VTR','U');self.ge(vp['s'],llput['e']+cfg.pump,active)
            self.add_interval('U',name,llput['s'],vp['e']+cfg.upper_reset*active,active)
            m.addCons(vp['s']-llput['e']<=cfg.module_residency+self.M*(1-active))
            vd=ev('destination_put','VTR','L');lpick=ev('lower_pick','ATR','L');home=ev('origin_put','ATR',origin)
            self.ge(lpick['s'],vd['e']+cfg.vent,active);self.ge(home['s'],lpick['e'],active)
            self.add_interval('L',name,vd['s'],lpick['e']+cfg.lower_reset*active,active)
            self.add_interval('ATR_hand',name+'_out',lpick['s'],home['e'],active)
            m.addCons(lpick['s']-vd['e']<=cfg.module_residency+self.M*(1-active))
            j.update(first=ap,last=home,upper_put=llput,lower_pick=lpick)
        else:
            vp=ev('source_pick','VTR','VS');vd=ev('destination_put','VTR','VS');j.update(first=vp,last=vd)
        ls=self.cont(name+'_ch_load_s');le=self.cont(name+'_ch_load_e');us=self.cont(name+'_ch_unload_s');ue=self.cont(name+'_ch_unload_e')
        for x in (ls,le,us,ue):m.addCons(x<=self.H*active)
        for p,selected in member.items():
            cond=self.and_(active,selected,f'route_select_{name}_{p}') if dummy_position is not None else selected
            for x,y in [(ls,self.load[p]['s']),(le,self.load[p]['e']),(us,self.unload[p]['s']),(ue,self.unload[p]['e'])]:self.eq(x,y,cond)
        self.ge(ls,vp['e'],active);self.ge(vd['s'],ue,active)
        self.add_interval('VTR_hand',name+'_in',vp['s'],le,active)
        self.add_interval('VTR_hand',name+'_out',us,vd['e'],active)
        j.update(source_pick=vp,destination_put=vd,load_s=ls,load_e=le,unload_s=us,unload_e=ue)
        self.jobs[name]=j

    def accompaniment(self):
        # If a selected P+D pair has both members on ATR before placing P on AL,
        # retain D on its gripper until P is retrieved, then place both in U.
        # Otherwise D enters U before that visit, or is picked after P reaches AL.
        self.escorts={}
        if self.cfg.source!='single' or self.cfg.dummy_alignment=='legacy_align_all':return
        for name,j in self.jobs.items():
            if j['product']:continue
            p,r=j['dummy_position']
            for w in self.products:
                pw=self.jobs[w.identifier]
                selected=self.and_(j['active'],self.pair.member[w.identifier,p,1-r],f'escort_pair_{name}_{w.identifier}')
                early=self.bit(f'direct_before_al_{name}_{w.identifier}')
                late=self.bit(f'direct_after_al_{name}_{w.identifier}')
                escort=self.bit(f'accompany_{name}_{w.identifier}')
                self.model.addCons(early+late+escort==selected)
                self.ge(pw['al_put']['s'],j['upper_put']['e'],early)
                self.ge(j['first']['s'],pw['al_put']['e'],late)
                self.ge(pw['al_put']['s'],j['first']['e'],escort)
                self.eq(j['upper_put']['s'],pw['upper_put']['s'],escort)
                self.eq(j['upper_put']['e'],pw['upper_put']['e'],escort)
                self.escorts[name,w.identifier]=escort

    def add_interval(self,resource,name,s,e,active):
        self.intervals.setdefault(resource,[]).append((name,s,e,active))
        if resource.endswith('_hand'):
            self.model.addCons(e-s<=self.cfg.robot_residency+self.M*(1-active))

    def capacity(self,name,intervals,slots,allowed=None):
        m=self.model;assign={}
        for key,s,e,a in intervals:
            for slot in range(slots):assign[key,slot]=a if slots==1 else self.bit(f'slot_{name}_{key}_{slot}')
            if slots>1:m.addCons(sum(assign[key,slot] for slot in range(slots))==a)
            if allowed is not None:
                for slot in range(slots):
                    if slot not in allowed[key]:m.addCons(assign[key,slot]==0)
        for (ki,si,ei,ai),(kj,sj,ej,aj) in combinations(intervals,2):
            if name.startswith('identity_'):
                key=(ki,kj)
                if ki.split('_')[0]==kj.split('_')[0]:continue
                if key not in self.dummy_orders:self.dummy_orders[key]=self.bit(f'order_identity_{ki}_{kj}')
                order=self.dummy_orders[key]
            else:order=self.bit(f'order_{name}_{ki}_{kj}')
            for slot in range(slots):
                x=assign[ki,slot];y=assign[kj,slot]
                m.addCons(sj>=ei-self.M*(3-x-y-order));m.addCons(si>=ej-self.M*(2-x-y+order))
        return assign

    def same_pair(self,j,k):
        choices=[]
        for p in set(j['member'])&set(k['member']):
            choices.append(self.and_(j['member'][p],k['member'][p],f'same_{j["name"]}_{k["name"]}_{p}'))
        return sum(choices)

    def resources(self):
        m=self.model;cfg=self.cfg;same={};active_pairs={}
        for robot,events in self.robots.items():
            changes={e['name']:(-2 if e['kind']=='pair_load' else 2 if e['kind']=='pair_unload' else 1 if e['kind'] in ('origin_pick','al_pick','source_pick','lower_pick') else -1) for e in events}
            before={e['name']:[] for e in events}
            for a,b in combinations(events,2):
                order=self.bit(f'order_{a["name"]}_{b["name"]}')
                aa=a['active'];bb=b['active']
                if isinstance(aa,int):both=bb
                elif isinstance(bb,int):both=aa
                elif aa.name==bb.name:both=aa
                else:
                    activation_key=tuple(sorted((aa.name,bb.name)))
                    if activation_key not in active_pairs:active_pairs[activation_key]=self.and_(aa,bb,'both_'+str(len(active_pairs)))
                    both=active_pairs[activation_key]
                if not isinstance(both,int):m.addCons(order<=both)
                before[b['name']].append(changes[a['name']]*order)
                before[a['name']].append(changes[b['name']]*(both-order))
                sync=0
                # Simultaneous same-location handling of members of one selected
                # pair is allowed, but never synchronizes unrelated material.
                if ('job' in a and 'job' in b and a['job']!=b['job'] and a['kind']==b['kind']
                    and a['location']==b['location'] and a['kind'] not in ('al_put','al_pick') and set(self.jobs[a['job']]['member'])&set(self.jobs[b['job']]['member'])):
                    key=tuple(sorted((a['job'],b['job'])))
                    if key not in same:same[key]=self.same_pair(self.jobs[key[0]],self.jobs[key[1]])
                    sync=self.bit('sync_'+a['name']+'_'+b['name']);m.addCons(sync<=same[key]);m.addCons(sync<=a['active']);m.addCons(sync<=b['active'])
                    self.eq(a['s'],b['s'],sync);self.eq(a['e'],b['e'],sync)
                for la,xa in a['location'].items():
                    for lb,xb in b['location'].items():
                        travel=0 if la==lb or {la,lb}<={'U','L'} else (cfg.atr_travel if robot=='ATR' else cfg.vtr_travel)
                        travel_ab=cfg.atr_empty_ll_to_lp if robot=='ATR' and la in ('U','L') and (lb.startswith('LP') or lb=='AS') and b['kind']=='origin_pick' else travel
                        travel_ba=cfg.atr_empty_ll_to_lp if robot=='ATR' and lb in ('U','L') and (la.startswith('LP') or la=='AS') and a['kind']=='origin_pick' else travel
                        inactive=4-a['active']-b['active']-xa-xb+sync
                        m.addCons(b['s']>=a['e']+travel_ab-self.M*(1-order+inactive))
                        m.addCons(a['s']>=b['e']+travel_ba-self.M*(order+inactive))
            # The robot executes a total order of positive-duration handling
            # groups. Net pickup/place changes exactly track carried wafers;
            # simultaneous groups contain at most two members of the same pair
            # with the same sign. Checking each prefix is equivalent to gripper
            # interval capacity, without assigning indistinguishable grippers.
            for e in events:
                load=sum(before[e['name']])+changes[e['name']]*e['active']
                self.ge(load,0,e['active']);self.ge(2 if robot=='ATR' else 4,load,e['active'])
        self.vtr_hands={}
        if cfg.vtr_hand_policy=='clean_dirty':
            allowed={}
            for name,j in self.jobs.items():
                allowed[name+'_in']=(0,1) if j['product'] else (0,1,2,3)
                allowed[name+'_out']=(2,3) if j['product'] else (0,1,2,3)
            self.vtr_hands=self.capacity('VTR_hand',self.intervals['VTR_hand'],4,allowed)
        for r,items in self.intervals.items():
            if r.endswith('_hand'):continue
            self.capacity(r,items,{'AL':1,'U':2,'L':2,'ATR_hand':2,'VTR_hand':4}[r])

    def result(self,solution=None):
        m=self.model;cfg=self.cfg;out={'schema':1,'config':asdict(cfg),'safe_candidate_bounds':self.safe_bounds,
            'candidate_pairs':self.P,'candidate_cycles':self.Q,'restricted_candidate_bounds':self.bounded,
            'status':str(m.getStatus()) if solution is None else 'assignment_check','solutions':m.getNSols() if solution is None else 1,'variables':self.original_dimensions['variables'],
            'constraints':self.original_dimensions['constraints'],'variable_types':self.original_dimensions['types'],'solve_seconds':m.getSolvingTime() if solution is None else 0,'dual_bound':m.getDualbound() if solution is None else None,
            'model_scope':'joint_event_model','cleaning_policy':'optional_before_threshold',
            'events':[],'pairs':[],'cycles':[],'jobs':[]}
        if solution is not None:out['solutions']=1
        if not out['solutions']:return out
        sol=solution if solution is not None else m.getBestSol();v=lambda x:float(x) if isinstance(x,(int,float)) else m.getSolVal(sol,x)
        out['cmax']=v(self.cmax);out['gap']=m.getGap() if solution is None else None
        for p,a in self.pair.active.items():
            if v(a)<.5:continue
            members=[]
            for r in (0,1):
                products=[w.identifier for w in self.products if v(self.pair.member[w.identifier,p,r])>.5]
                ds=[t for t,j,k in self.pair.dummy_identity if j==p and k==r and v(self.pair.dummy_identity[t,j,k])>.5]
                members.append((products+ds)[0])
            out['pairs'].append(dict(id=p,members=members,chamber=next(c for c in cfg.chambers if v(self.pair.chamber[p,c])>.5),mode=next(k for k in ('4x1','2x2','clean') if v(self.pair.mode[p,k])>.5)))
        for e in self.events:
            if v(e['active'])>.5:
                out['events'].append({k:e[k] for k in ('name','kind','robot','job','pair','chamber','cycle') if k in e}|dict(start=v(e['s']),end=v(e['e']),location=next(n for n,x in e['location'].items() if v(x)>.5)))
        for c in cfg.chambers:
            for q in range(self.Q):
                if v(self.cy.used[c,q])<.5:continue
                out['cycles'].append(dict(chamber=c,index=q,mode=next(k for k in ('4x1','2x2','clean') if v(self.cy.kind[c,q,k])>.5),start=v(self.cy.start[c,q]),end=v(self.cy.end[c,q]),counter=v(self.cy.counter[c,q]),pairs=[p for p in range(self.P) if v(self.cy.occupancy[p,c,q])>.5],front=next(p for p in range(self.P) if v(self.front[p,c,q])>.5)))
        for name,j in self.jobs.items():
            if v(j['active'])<.5:continue
            pair=next(p for p,x in j['member'].items() if v(x)>.5)
            if j['product']:identity=j['product']
            else:
                pp,r=j['dummy_position'];identity=next(t for t,p0,r0 in self.pair.dummy_identity if p0==pp and r0==r and v(self.pair.dummy_identity[t,p0,r0])>.5)
            out['jobs'].append(dict(name=name,identity=identity,product=bool(j['product']),pair=pair,origin=j['origin'],loan_start=v(j['first']['s']),loan_end=v(j['last']['e']),load_start=v(j['load_s']),load_end=v(j['load_e']),unload_start=v(j['unload_s']),unload_end=v(j['unload_e'])))
            if cfg.vtr_hand_policy=='clean_dirty':
                from grippers import HANDS
                for leg in ('in','out'):
                    out['jobs'][-1]['vtr_hand_'+leg]=next(HANDS[g] for g in range(4) if v(self.vtr_hands[name+'_'+leg,g])>.5)
        return out
