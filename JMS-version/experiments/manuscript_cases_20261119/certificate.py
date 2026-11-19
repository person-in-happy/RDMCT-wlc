"""SCIP refinement on active indices and streamed checks of the original full D/E models."""
from collections import Counter
from contextlib import ExitStack
from dataclasses import replace
import gc
import gzip
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import model
import joint_pairing_model
import joint_chamber_cycle_model
from validate import validate
from finite_budget import physical_metrics
from grouping import GAP

TOL=2e-4


class Value(float):
    """Retain named-variable identity and SCIP-scale tolerance in streamed row comparisons."""
    __slots__=()
    def __add__(self,b): return Value(float(self)+float(b))
    __radd__=__add__
    def __sub__(self,b): return Value(float(self)-float(b))
    def __rsub__(self,a): return Value(float(a)-float(self))
    def __mul__(self,b): return Value(float(self)*float(b))
    __rmul__=__mul__
    def __neg__(self): return Value(-float(self))
    def __le__(self,b): return float(self)<=float(b)+TOL
    def __ge__(self,b): return float(self)>=float(b)-TOL
    def __eq__(self,b): return abs(float(self)-float(b))<=TOL
    __hash__=float.__hash__


class RowsDone(Exception):
    pass


class FullCheck:
    def __init__(self,values):
        self.values, self.types, self.rows, self.nonzero = values,Counter(),0,{}

    def hideOutput(self):
        pass

    def addVar(self,name,vtype="C",lb=0,ub=None):
        v=self.values.get(name,0.)
        hi=1 if vtype=="B" else ub
        if v<lb-TOL or (hi is not None and v>hi+TOL) or (vtype!="C" and abs(v-round(v))>1e-5):
            raise ValueError(f"Full model domain failed for {name}: {v}")
        self.types[vtype]+=1
        if v:
            self.nonzero[name]=v
        return Value(v)

    def addCons(self,satisfied,name=None):
        self.rows+=1
        if satisfied is not True:
            frame=sys._getframe(1)
            keys={k:str(frame.f_locals[k])[:80] for k in ("p","q","c","name","key") if k in frame.f_locals}
            raise ValueError(f"Full row {self.rows} failed at {frame.f_code.co_filename}:{frame.f_lineno}, {name}, {keys}")

    def setObjective(self,obj,sense):
        if sense!="minimize" or abs(obj-self.values["Cmax"])>TOL:
            raise ValueError("Full primary objective mismatch")
        raise RowsDone


def full_check(cfg,values,data):
    active=FullCheck(values)
    api=SimpleNamespace(Model=lambda _:active,quicksum=sum)
    with ExitStack() as stack:
        for module in (model,joint_pairing_model,joint_chamber_cycle_model):
            stack.enter_context(patch.object(module,"scip",api))
        try:
            model.Integrated(cfg)
        except RowsDone:
            pass
        else:
            raise ValueError("The full row generator exited before setting its objective")
    if abs(float(active.values["Cmax"])-data["cmax"])>TOL:
        raise ValueError("Full assignment differs from the physical product return")
    check=validate(data)
    if not check["valid"]:
        raise ValueError(str(check["errors"][:5]))
    return dict(valid=True,rows=active.rows,variables=sum(active.types.values()),types=dict(active.types),
                absolute_row_tolerance=TOL,replay=check), active.nonzero


def save_values(path,values):
    tmp=path.with_suffix(".tmp")
    with gzip.open(tmp,"wt",encoding="utf-8") as stream:
        json.dump({"default":0,"nonzero":values},stream,allow_nan=False,separators=(",",":"))
    tmp.replace(path)


class Reduced:
    """Substitute constants while the unchanged backend emits the active-index model."""
    def __init__(self, known, choose):
        from scip_imports import scip
        self.native=scip.Model("manuscript_fixed_structure")
        self.native.hideOutput()
        self.known,self.choose,self.constants=known,choose,{}
        self.redundant_rows=0

    def __getattr__(self,name):
        return getattr(self.native,name)

    def addVar(self,name,vtype="C",lb=0,ub=None):
        if self.choose(name,vtype):
            value=self.known.get(name,0.)
            if value:
                self.constants[name]=value
            return MixedValue(value)
        return self.native.addVar(name=name,vtype=vtype,lb=lb,ub=ub)

    def addCons(self,row,name=None):
        if isinstance(row,bool):
            if not row:
                frame=sys._getframe(1)
                raise ValueError(f"Fixed input contradicts {frame.f_code.co_filename}:{frame.f_lineno} ({name})")
            return None
        # Drop linear inequalities already implied by the original variable
        # bounds. Inactive big-M rows otherwise dominate the native matrix.
        low=high=0.
        for term,coef in row.expr.terms.items():
            if not term.vartuple:
                low+=coef
                high+=coef
                continue
            (var,)=term.vartuple
            a,b=var.getLbOriginal(),var.getUbOriginal()
            if coef<0: a,b=b,a
            low+=coef*a
            high+=coef*b
        if (row._lhs is None or low>=row._lhs) and (row._rhs is None or high<=row._rhs):
            self.redundant_rows+=1
            return None
        return self.native.addCons(row,name=name or "")


class MixedValue(float):
    """Fold numerical rows with feasibility tolerance and defer symbolic operations to SCIP."""
    __slots__=()
    def __add__(self,b):
        return MixedValue(float(self)+float(b)) if isinstance(b,(int,float)) else NotImplemented
    __radd__=__add__
    def __sub__(self,b):
        return MixedValue(float(self)-float(b)) if isinstance(b,(int,float)) else NotImplemented
    def __rsub__(self,a):
        return MixedValue(float(a)-float(self)) if isinstance(a,(int,float)) else NotImplemented
    def __mul__(self,b):
        return MixedValue(float(self)*float(b)) if isinstance(b,(int,float)) else NotImplemented
    __rmul__=__mul__
    def __neg__(self): return MixedValue(-float(self))
    def __le__(self,b):
        return float(self)<=float(b)+TOL if isinstance(b,(int,float)) else NotImplemented
    def __ge__(self,b):
        return float(self)>=float(b)-TOL if isinstance(b,(int,float)) else NotImplemented
    def __eq__(self,b):
        return abs(float(self)-float(b))<=TOL if isinstance(b,(int,float)) else NotImplemented
    __hash__=float.__hash__


def reduced_model(cfg,known,choose):
    result=Reduced(known,choose)
    api=SimpleNamespace(Model=lambda _:result,quicksum=sum)
    with ExitStack() as stack:
        for module in (model,joint_pairing_model,joint_chamber_cycle_model):
            stack.enter_context(patch.object(module,"scip",api))
        instance=model.Integrated(cfg)
    m=result.native
    m.setIntParam("parallel/maxnthreads",1)
    m.setIntParam("lp/threads",1)
    m.setIntParam("randomization/randomseedshift",1)
    m.setRealParam("limits/memory",256)
    m.setRealParam("limits/gap",GAP)
    m.setRealParam("limits/time",60)
    return instance,result


def physical_fixes(cfg,schedule):
    from pjobs import task_for_product
    groups=task_for_product(cfg)
    by_pair={p["id"]:p for p in schedule["pairs"]}
    known={"Cmax":schedule["cmax"]}
    for p,pair in by_pair.items():
        known[f"jp_active_{p}"]=known[f"jp_mode_{p}_{pair['mode']}"]=known[f"jp_chamber_{p}_{pair['chamber']}"]=1
        for r,w in enumerate(pair["members"]):
            if w in groups:
                known[f"pj_x_{groups[w].identifier}_{p}_{r}"]=1
                if r==1: known[f"pj_product_{p}_1"]=1
            else:
                known[f"jp_identity_{w}_{p}_{r}"]=1
    clocks=set()
    for e in schedule["events"]:
        clocks.add(e["name"]+"_s")
        known[e["name"]+"_s"]=e["start"]
    # Robot ordering is determined by the supplied handling times. A stable
    # tie order represents simultaneous same-pair pickups or placements.
    for robot in ("ATR","VTR"):
        events=sorted((e for e in schedule["events"] if e["robot"]==robot),
                      key=lambda e:(e["start"],e["name"]))
        for index,first in enumerate(events):
            for later in events[index+1:]:
                known[f"order_{first['name']}_{later['name']}"]=1
    for j in schedule["jobs"]:
        for prefix,field in (("ch_load","load_start"),("ch_unload","unload_start")):
            key=f"{j['name']}_{prefix}_s"
            clocks.add(key)
            known[key]=j[field]
    for c in schedule["cycles"]:
        ch,q=c["chamber"],c["index"]
        known[f"jc_kind_{ch}_{q}_{c['mode']}"]=1
        known[f"jc_start_{ch}_{q}"]=c["start"]
        clocks.add(f"jc_start_{ch}_{q}")
        for p in c["pairs"]:
            known[f"jc_occ_{p}_{ch}_{q}"]=1
        known[f"front_{c['front']}_{ch}_{q}"]=1
    metrics=physical_metrics(schedule)
    known["max_wait"]=metrics["wait_max"]
    history={}
    for c in sorted(schedule["cycles"],key=lambda x:(x["chamber"],x["index"])):
        ch,q=c["chamber"],c["index"]
        history[ch,q]=c
        if q>=2:
            a,b=history[ch,q-2],history[ch,q-1]
            if (all(x["mode"]=="2x2" for x in (a,b,c)) and set(a["pairs"])&set(b["pairs"])
                    and set(b["pairs"])&set(c["pairs"])):
                known[f"rhythm_{ch}_{q}"]=abs(c["start"]-2*b["start"]+a["start"])
    return known,clocks


def projected_refinement(cfg,stage_a):
    from seed import normalize_schedule
    stage_a=normalize_schedule(cfg,stage_a)
    p=max(sum(j["product"] for j in stage_a["jobs"]),max(x["id"] for x in stage_a["pairs"])+1)
    q=max(x["index"] for x in stage_a["cycles"])+2
    compact=replace(cfg,max_pairs=p,max_cycles=q)
    known,clocks=physical_fixes(cfg,stage_a)
    structural=("jp_active_","jp_mode_","jp_chamber_","jp_identity_","pj_x_","pj_product_",
                "jc_occ_","jc_kind_","front_")
    def fix_primary(name,typ):
        robot_order=(name.startswith("order_") and not name.startswith(
            ("order_identity_","order_U_","order_L_","order_AL_","order_VTR_hand_","order_ATR_hand_")))
        return (robot_order or name.startswith(structural) or (typ=="C" and
                (name.endswith("_s") or name.startswith(("jc_start_","rhythm_")) or name in ("Cmax","max_wait"))))
    x,sub=reduced_model(compact,known,fix_primary)
    try:
        m=sub.native
        m.setObjective(0,"minimize")
        m.optimize()
        if not m.getNSols():
            raise ValueError(f"Could not complete phase A assignment: {m.getStatus()}")
        sol=m.getBestSol()
        if not m.checkSol(sol,completely=True,original=True):
            raise ValueError("Native phase A completion failed")
        a_values=dict(sub.constants)
        a_values.update((v.name,m.getSolVal(sol,v)) for v in m.getVars(transformed=False))
        native_a=x.result(solution=sol)
        for e in stage_a["events"]:
            if abs(a_values.get(e["name"]+"_s",0.)-e["start"])>TOL:
                raise ValueError("Completion changed an active event time")
    finally:
        sub.native.freeProb()
    del x,sub,m,sol
    gc.collect()
    native_a["config"]=stage_a["config"]
    a_metrics=physical_metrics(native_a)
    for key,expected in physical_metrics(stage_a).items():
        if abs(a_metrics[key]-expected)>TOL:
            raise ValueError(f"Reconstruction changed {key}")
    jobs={j["name"]:j["pair"] for j in stage_a["jobs"]}
    possible_sync=set()
    for i,e in enumerate(stage_a["events"]):
        for other in stage_a["events"][:i]:
            if ("job" in e and "job" in other and e["job"]!=other["job"]
                    and jobs[e["job"]]==jobs[other["job"]] and e["kind"]==other["kind"]
                    and e["location"]==other["location"]):
                possible_sync.update((f"sync_{e['name']}_{other['name']}",f"sync_{other['name']}_{e['name']}"))
    def fix_secondary(name,typ):
        if typ!="C": return name not in possible_sync
        return (name.endswith("_s") or name.startswith("jc_start_")) and name not in clocks
    x,sub=reduced_model(compact,a_values,fix_secondary)
    try:
        m=sub.native
        m.addCons(x.cmax<=a_metrics["cmax"]+1e-6)
        m.setObjective(x.secondary_objective,"minimize")
        warm=m.createSol()
        for v in m.getVars(transformed=False):
            m.setSolVal(warm,v,a_values.get(v.name,0.))
        if not m.checkSol(warm,completely=True,original=True):
            raise ValueError("Projected phase B rejected the phase A witness")
        m.addSol(warm)
        m.optimize()
        sol=m.getBestSol()
        if sol is None or not m.checkSol(sol,completely=True,original=True):
            raise ValueError("Native phase B failed")
        data=x.result(solution=sol)
        data["config"]=stage_a["config"]
        metrics=physical_metrics(data)
        obj=m.getSolObjVal(sol)
        if (abs(metrics["secondary"]-obj)>TOL or metrics["cmax"]>a_metrics["cmax"]+TOL
                or metrics["secondary"]>a_metrics["secondary"]+TOL):
            raise ValueError(f"Physical objective mismatch {metrics}, {obj}")
        b_values=dict(sub.constants)
        b_values.update((v.name,m.getSolVal(sol,v)) for v in m.getVars(transformed=False))
        b_values["Cmax"]=data["cmax"]=metrics["cmax"]
        record=dict(status=str(m.getStatus()),gap_limit=m.getParam("limits/gap"),seconds=m.getSolvingTime(),
                    time_limit_s=m.getParam("limits/time"),primal=obj,dual=m.getDualbound(),relative_gap=m.getGap(),
                    makespan_cap=a_metrics["cmax"]+1e-6,active_model_pairs=p,active_model_cycles_per_chamber=q,
                    scope="fixed phase-A discrete choices except intra-pair synchronization, active pair/cycle indices",
                    compact_native_row_check=True,removed_domain_implied_rows=sub.redundant_rows,
                    native_variables=x.original_dimensions["variables"],native_rows=x.original_dimensions["constraints"])
    finally:
        sub.native.freeProb()
    return native_a,a_values,data,b_values,record


def refine(cfg,stage_a,dest):
    a,av,b,bv,result=projected_refinement(cfg,stage_a)
    for tag,values,sched in (("primary",av,a),("final",bv,b)):
        cert,nonzero=full_check(cfg,values,sched)
        save_values(dest/f"{tag}_assignment.json.gz",nonzero)
        result[f"{tag}_certificate"]=cert
        sched.update(original_model_check=True,validation=cert["replay"],global_optimality_claim=False,
                     model_scope="fixed-structure timing, verified in the unrestricted original model")
    return a,b,result
