"""Checked integer export of the original event model, not a new scheduler."""
import math
from ortools.sat.python import cp_model


def export_model(x,hint):
    m=x.model;cfg=x.cfg
    for key,value in vars(cfg).items():
        if isinstance(value,(int,float)) and abs(value-round(value))>1e-8:
            raise ValueError('Integer-time theorem requires integer parameter '+key)
    variables={v.name:v for v in m.getVars(transformed=False)}
    derived={v.name for v in x.waits+x.rhythm+[x.max_wait]}
    cp=cp_model.CpModel();vmap={}
    for name,v in variables.items():
        if abs(v.getLbOriginal()-round(v.getLbOriginal()))>1e-8:
            raise ValueError('Noninteger time lower bound: '+name)
        delta=v.getUbOriginal()-round(v.getUbOriginal())
        if abs(delta)>1e-8 and abs(delta-1e-6)>1e-8:
            raise ValueError('Noninteger time upper bound: '+name)
        lo=math.ceil(v.getLbOriginal()-1e-8);hi=math.floor(v.getUbOriginal()+1e-8)
        vmap[name]=cp.new_bool_var(name) if v.vtype()=='BINARY' and (lo,hi)==(0,1) else cp.new_int_var(lo,hi,name)
    audit=dict(schema=1,physical_difference_rows=0,derived_helper_rows=0,integer_only_rows=0,
               normalized_cutoff_slack_coefficients=0,variables=len(vmap),constraints=0,
               theorem='integer_timing_by_flooring_v1',complete_integer_hint=True)
    rounded={}
    for name,v in variables.items():
        value=hint.get(name)
        if value is not None and abs(value-round(value))<1e-7:
            rounded[name]=round(value);cp.add_hint(vmap[name],round(value))
        else:audit['complete_integer_hint']=False
    for cons in m.getConss():
        if cons.getConshdlrName()!='linear':raise ValueError('Unsupported constraint '+cons.name)
        row=m.getValsLinear(cons);coeffs={}
        lhs=m.getLhs(cons);rhs=m.getRhs(cons)
        if abs(lhs)<1e19 and abs(lhs-round(lhs))>1e-8 and abs(lhs-round(lhs)+1e-6)>1e-8:
            raise ValueError('Noninteger row lower bound: '+cons.name)
        if abs(rhs)<1e19 and abs(rhs-round(rhs))>1e-8 and abs(rhs-round(rhs)-1e-6)>1e-8:
            raise ValueError('Noninteger row upper bound: '+cons.name)
        for name,value in row.items():
            integer=round(value)
            if abs(value-integer)>1e-8:
                # strengthen() adds only this outward epsilon to used-cycle UB.
                if not (name.startswith('jc_used_') and abs(value-integer+1e-6)<1e-8 and lhs<=-1e19 and rhs==0):
                    raise ValueError(f'Unexpected fractional coefficient: {cons.name} {name} {value}')
                audit['normalized_cutoff_slack_coefficients']+=1
            coeffs[name]=integer
        continuous={n:v for n,v in coeffs.items() if variables[n].vtype()=='CONTINUOUS' and v}
        if any(n in derived for n in continuous):
            helpers={n:v for n,v in continuous.items() if n in derived}
            physical={n:v for n,v in continuous.items() if n not in derived}
            waits={n:v for n,v in helpers.items() if n in {v.name for v in x.waits}}
            rhythms={n:v for n,v in helpers.items() if n in {v.name for v in x.rhythm}}
            wait_equality=(len(waits)==len(helpers)==1 and list(waits.values())==[1]
                           and sorted(physical.values())==[-1,1] and lhs==rhs and rhs<=0)
            maximum=(len(helpers)==2 and not physical and len(waits)==1
                     and helpers.get(x.max_wait.name)==1 and list(waits.values())==[-1]
                     and lhs==0 and rhs>=1e19)
            rhythm=(len(rhythms)==len(helpers)==1 and list(rhythms.values())==[1]
                    and sorted(physical.values()) in ([-2,1,1],[-1,-1,2])
                    and all(n.startswith('jc_start_') for n in physical))
            if not (wait_equality or maximum or rhythm):
                raise ValueError(f'Unrecognized derived timing constraint: {cons.name} {continuous} [{lhs},{rhs}]')
            audit['derived_helper_rows']+=1
        elif continuous:
            vals=list(continuous.values())
            if len(vals)>2 or any(abs(v)!=1 for v in vals) or (len(vals)==2 and sum(vals)!=0):
                raise ValueError('Physical timing is not a difference system: '+cons.name)
            audit['physical_difference_rows']+=1
        else:audit['integer_only_rows']+=1
        lo=cp_model.INT_MIN if lhs<=-1e19 else math.ceil(lhs-1e-8)
        hi=cp_model.INT_MAX if rhs>=1e19 else math.floor(rhs+1e-8)
        expr=cp_model.LinearExpr.weighted_sum([vmap[n] for n in coeffs],list(coeffs.values()))
        cp.add_linear_constraint(expr,lo,hi)
        audit['constraints']+=1
        if audit['complete_integer_hint']:
            activity=sum(v*rounded[n] for n,v in coeffs.items())
            if not lo<=activity<=hi:audit['complete_integer_hint']=False
    cp.minimize(vmap[x.cmax.name])
    error=cp.validate()
    if error:raise ValueError(error)
    return cp,vmap,audit
