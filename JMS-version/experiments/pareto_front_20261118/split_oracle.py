"""Continuous-time lower-bound oracle for both PD pairs; competition region A<=528, B<=376/3."""
from itertools import combinations
import math
import numpy as np
from scip_imports import scip

PATTERNS=('AABB','ABAB','ABBA')
ATR=('origin_pick','al_put','al_pick','upper_put','lower_pick','origin_put')
VTR=('hs','hl','ps','ds','pl','hu','hd','ts','tl','tu','td','pu','pv','dv')

class SplitOracle:
    def __init__(self,cfg,pattern,acap,bcap):
        self.cfg=cfg
        assert pattern in PATTERNS and acap<=528.00005 and bcap<=376/3+.001
        assert (cfg.mix_time,cfg.rotation,cfg.handling,cfg.atr_handling,cfg.atr_travel,cfg.atr_empty_ll_to_lp,cfg.vtr_travel,cfg.pump,cfg.vent,cfg.alignment,cfg.module_residency,cfg.robot_residency)==(90,2,1,4,3,6,2,30,25,20,100,100)
        self.events=['zero'];self.robot={};self.loc={};self.duration={'zero':0};self.rows=[];self.waits=[]
        self.acap,self.bcap=acap,bcap
        self.wait_upper=max(3,(bcap-12)/10)
        locs=['VS','CH','U','VS','CH','CH','VS','VS','CH','CH','VS','CH','L','VS']
        for k in range(2):
            for name,loc in zip(VTR,locs):self.event(k,name,'VTR',f'CH{k}' if loc=='CH' else loc,1)
            for name,loc in zip(ATR,('LP','AL','AL','U','L','LP')):self.event(k,name,'ATR',loc,4)
        exposure={}
        for k in range(2):
            def n(a):return (k,a)
            def edge(a,b,d):self.rows.append((n(a),n(b),d))
            def wait(a,b,d,mult=1):
                edge(a,b,d);edge(b,a,-d-self.wait_upper)
                self.waits.append((n(a),n(b),d,mult))
            for a,b,d,mult in [('hs','hl',3,2),('hu','hd',3,2),('ts','tl',3,2),('tu','td',3,2),
                               ('ps','pl',3,1),('ds','pl',3,1),('pu','pv',3,1),('pu','dv',3,1),
                               ('origin_pick','al_put',7,1),('al_put','al_pick',24,1),('al_pick','upper_put',7,1),
                               ('upper_put','ps',34,1),('pv','lower_pick',26,1),('lower_pick','origin_put',7,1)]:
                wait(a,b,d,mult)
            # Head DD load; rotate; PD first exposure; rotate; unload old DD; tail DD load;
            # second exposure; unload DD; rotate; unload the retained PD.
            for a,b,d in [('hl','pl',3),('pl','hu',93),('hu','tl',1),('tl','tu',91),('tu','pu',3),
                          ('hu','hl',-191),('pu','pl',-281),('tu','tl',-191),
                          ('hd','ts',1)]:
                edge(a,b,d)
            for a,b in [('ps','pl'),('ds','pl'),('hs','hl'),('ts','tl'),('hu','hd'),('tu','td'),('pu','pv'),('pu','dv')]:
                edge(b,a,-99)
            self.rows.append((n('origin_put'),'zero',4-acap))
            exposure[k]=[n('pl'),n('tl')]
        seq=[exposure[int(letter=='B')].pop(0) for letter in pattern]
        self.rows.extend((a,b,90) for a,b in zip(seq,seq[1:]))
        self.byrobot={r:[e for e in self.events if self.robot.get(e)==r] for r in ('VTR','ATR')}
        for e in self.events[1:]:self.rows.extend([('zero',e,0),(e,'zero',-(acap+100))])
        self.index={e:i for i,e in enumerate(self.events)}
        self.model=m=scip.Model();m.hideOutput()
        self.t={e:m.addVar(lb=0,ub=0 if e=='zero' else acap+100,name='t'+str(i)) for i,e in enumerate(self.events)}
        self.avar=m.addVar(lb=0,ub=acap,name='A')
        self.w=m.addVar(lb=3,ub=self.wait_upper+1e-7,name='max_wait')
        self.bvar=m.addVar(lb=42,ub=bcap,name='B')
        for k in range(2):m.addCons(self.avar>=self.t[k,'origin_put']+4)
        total=0
        for i,j,d,mult in self.waits:
            gap=self.t[j]-self.t[i]-d
            m.addCons(self.w>=gap);total+=mult*gap
        m.addCons(self.bvar==total+10*self.w)
        for k in range(2):
            for items in [[('ps','pl'),('ds','pl')],[('pu','pv'),('pu','dv')]]:
                m.addCons(sum(self.t[k,b]-self.t[k,a]-3 for a,b in items)>=3)
        clos,forced=self.propagate()
        self.impossible=clos is None
        if self.impossible:return
        for i,j,d in self.rows:m.addCons(self.t[j]>=self.t[i]+d)
        for e in self.events[1:]:
            i=self.index[e];m.chgVarLb(self.t[e],max(0,clos[0,i]));m.chgVarUb(self.t[e],min(acap+100,-clos[i,0]))
        orders={}
        for robot,es in self.byrobot.items():
            for a,b in combinations(es,2):
                i,j=self.index[a],self.index[b];dab,dba=self.travel(a,b),self.travel(b,a)
                if (a,b) in forced:
                    orders[a,b]=int(forced[a,b]);continue
                z=m.addVar(vtype='B',name=f'b{i}_{j}')
                orders[a,b]=z
                m.addCons(self.t[b]>=self.t[a]+dab-max(0,dab-clos[i,j])*(1-z))
                m.addCons(self.t[a]>=self.t[b]+dba-max(0,dba-clos[j,i])*z)
        # AL occupancy is exclusive until the aligned wafer has been picked up.
        a0,b0=(0,'al_put'),(1,'al_put')
        z=orders[a0,b0]
        for k,z0 in [(0,z),(1,1-z)]:
            a=(k,'al_pick');b=(1-k,'al_put')
            m.addCons(self.t[b]>=self.t[a]+4-(4-clos[self.index[a],self.index[b]])*(1-z0) if clos[self.index[a],self.index[b]]<4 else self.t[b]>=self.t[a]+4)
        es=self.byrobot['VTR']
        ranks={e:i for i,e in enumerate(es)}
        def earlier(f,e):return orders[f,e] if ranks[f]<ranks[e] else 1-orders[e,f]
        for changes,cap in [
          ({'hs':2,'ts':2,'ds':1,'hd':-2,'td':-2,'dv':-1},4),
          ({'hs':2,'ts':2,'ps':1,'ds':1,'hl':-2,'pl':-2,'tl':-2,'hu':2,'tu':2,'pu':2,'hd':-2,'td':-2,'pv':-1,'dv':-1},4)]:
            items=[(e,changes[e[1]]) for e in es if e[1] in changes]
            for e,v in items:
                count=v+scip.quicksum(inc*earlier(f,e) for f,inc in items if f!=e)
                m.addCons(count<=cap);m.addCons(count>=0)
        # The two helpers cannot overlap the PD's dummy plus each other in one block.
        # This is already accounted for by hd -> ts and the inventory prefixes.

    def event(self,k,act,robot,loc,d):
        e=(k,act);self.events.append(e);self.robot[e]=robot;self.loc[e]=loc;self.duration[e]=d

    def travel(self,a,b):
        la,lb=self.loc[a],self.loc[b];r=self.robot[a]
        move=0 if la==lb or {la,lb}<={'L','U'} else (2 if r=='VTR' else 3)
        if r=='ATR' and la in ('U','L') and lb=='LP' and b[1]=='origin_pick':move=6
        return self.duration[a]+move

    def propagate(self):
        n=len(self.events);forced={}
        while True:
            mat=np.full((n,n),-math.inf);np.fill_diagonal(mat,0.)
            for a,b,d in self.rows:
                i,j=self.index[a],self.index[b];mat[i,j]=max(mat[i,j],d)
            for k in range(n):mat=np.maximum(mat,mat[:,k,None]+mat[None,k,:])
            if np.max(np.diag(mat))>1e-6:return None,None
            changed=False
            for es in self.byrobot.values():
                for a,b in combinations(es,2):
                    if (a,b) in forced:continue
                    i,j=self.index[a],self.index[b];da,db=self.travel(a,b),self.travel(b,a)
                    if mat[i,j]+db>1e-7:
                        forced[a,b]=True;self.rows.append((a,b,da));changed=True
                    elif mat[j,i]+da>1e-7:
                        forced[a,b]=False;self.rows.append((b,a,db));changed=True
            if not changed:return mat,forced

    def solve(self,job,seconds,logfile=None):
        m=self.model
        if self.impossible:return dict(status='infeasible_by_precedence',seconds=0.,bound=None)
        kind=job[0]
        if kind=='A':obj=self.avar
        elif kind=='B':obj=self.bvar
        elif kind=='gap':
            obj=m.addVar(lb=0,ub=1000,name='strict_gap')
            m.addCons(self.avar+obj<=job[1]);m.addCons(self.bvar+obj<=job[2])
        elif kind=='line':obj=job[1]*self.avar+job[2]*self.bvar
        else:raise ValueError(job)
        m.setObjective(obj,'maximize' if kind=='gap' else 'minimize')
        m.setRealParam('limits/time',seconds);m.setRealParam('numerics/feastol',1e-8);m.setIntParam('parallel/maxnthreads',1)
        if logfile:m.setLogfile(str(logfile))
        m.optimize()
        bound=m.getDualbound()
        row=dict(status=str(m.getStatus()),seconds=m.getSolvingTime(),bound=bound if abs(bound)<1e19 else None,nodes=m.getNNodes())
        if m.getNSols():
            s=m.getBestSol();t={e:m.getSolVal(s,v) for e,v in self.t.items()}
            row.update(value=m.getObjVal(),A=max(t[k,'origin_put']+4 for k in range(2)),
              B=sum(mult*(t[j]-t[i]-d) for i,j,d,mult in self.waits)+10*max(t[j]-t[i]-d for i,j,d,_ in self.waits),
              times=[{act:t[k,act] for act in (*ATR,*VTR)} for k in range(2)])
        return row

