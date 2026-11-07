"""Qualified physical seeds and temporary assignment completion for Model4."""
from collections import defaultdict
from dataclasses import replace,asdict
import copy
from pjobs import products_from_load_ports,groups_from_config,task_for_product
from physical_seed import construct as physical_construct


def normalize_schedule(cfg,data):
    """Relabel interchangeable pair/dummy slots, then canonically decode products."""
    out=copy.deepcopy(data);groups=task_for_product(cfg);n=len(groups)
    product_pairs=[p for p in data['pairs'] if any(w in groups for w in p['members'])]
    auxiliary_pairs=[p for p in data['pairs'] if not any(w in groups for w in p['members'])]
    pairmap={p['id']:i for i,p in enumerate(sorted(product_pairs,key=lambda p:p['id']))}
    pairmap.update({p['id']:n+i for i,p in enumerate(sorted(auxiliary_pairs,key=lambda p:p['id']))})
    positions={}
    for p in out['pairs']:
        old=p['id'];p['id']=pairmap[old]
        p['members'].sort(key=lambda w:w not in groups)
        for r,w in enumerate(p['members']):positions[old,w]=r
    out['pairs'].sort(key=lambda p:p['id'])
    dummy_map={}
    for p in out['pairs']:
        for w in p['members']:
            if w not in groups and w not in dummy_map:dummy_map[w]=f'D{len(dummy_map)+1}'
    jobmap={};ordered=defaultdict(list)
    pick={e['job']:e['start'] for e in data['events'] if e['kind']=='origin_pick'}
    for j in out['jobs']:
        old=j['pair'];w=j['identity'];r=positions[old,w];j['pair']=pairmap[old]
        name=f'{"prod" if j["product"] else "aux"}_{j["pair"]}_{r}'
        jobmap[j['name']]=name
        if j['product']:ordered[groups[w].identifier].append((pick[j['name']],j['pair'],r,w))
        j['name']=name
    product_map={}
    for g in groups_from_config(cfg):
        selected=sorted(ordered[g.identifier])
        if len(selected)!=g.count:raise ValueError('Seed inventory differs from Pjob input')
        product_map.update((old[-1],label) for old,label in zip(selected,g.labels))
    for p in out['pairs']:p['members']=[product_map.get(w,dummy_map.get(w,w)) for w in p['members']]
    for j in out['jobs']:
        old=j['identity'];j['identity']=product_map.get(old,dummy_map.get(old,old))
        if j['product']:
            g=groups[j['identity']];j['pjob']=g.pjob;j['wafer_number']=25*(g.load_port-1)+int(j['identity'].split('_W')[1])
    for e in out['events']:
        if 'job' in e:e['job']=jobmap[e['job']];e['name']=e['job']+'_'+e['kind']
        if 'pair' in e:e['pair']=pairmap[e['pair']];e['name']=('load_' if e['kind']=='pair_load' else 'unload_')+str(e['pair'])
    for c in out['cycles']:c['pairs']=[pairmap[p] for p in c['pairs']];c['front']=pairmap[c['front']]
    out['config']=asdict(cfg);out['model_scope']='model4_pjob_physical_reference'
    out.pop('validation',None)
    from pjob_order import encoding,order_report
    codes=encoding(cfg);out['product_encoding']=codes
    out['model_scope']='pjob_global_fifo_physical_reference_v2'
    for job in out['jobs']:
        if job['product']:job.update(codes[job['identity']])
    ordered=order_report(out)
    if not ordered['valid']:raise ValueError(ordered['errors'])
    return out


def make_template_contiguous(data):
    template=copy.deepcopy(data);mapping={p['id']:i for i,p in enumerate(sorted(template['pairs'],key=lambda p:p['id']))}
    for p in template['pairs']:p['id']=mapping[p['id']]
    for c in template['cycles']:c['pairs']=[mapping[p] for p in c['pairs']];c['front']=mapping[c['front']]
    return template


def construct(cfg,template=None,balanced=False):
    if template is not None:
        result=physical_construct(cfg,make_template_contiguous(template))
    else:
        byid=task_for_product(cfg);work={c:0 for c in cfg.chambers};assigned={c:[] for c in cfg.chambers}
        bytask=defaultdict(list)
        for w in products_from_load_ports(cfg.load_ports):bytask[byid[w.identifier].pjob].append(w)
        for ws in bytask.values():
            allowed=sorted(byid[ws[0].identifier].chambers)
            chunks=[ws[start:start+2] for start in range(0,len(ws),2)]
            # Each chamber receives a consecutive product-index segment.
            # The serial template visits chambers in increasing order.
            if balanced:
                count,extra=divmod(len(chunks),len(allowed))
                destinations=[c for i,c in enumerate(allowed) for _ in range(count+(i<extra))]
            else:destinations=[allowed[0]]*len(chunks)
            for pair,c in zip(chunks,destinations):
                assigned[c].extend(pair);work[c]+=cfg.full_time if pair[0].mode=='4x1' else 2*cfg.mix_time
        template={'pairs':[],'cycles':[]}
        for c,ws in assigned.items():
            if not ws:continue
            ports={f'LP{i}':{'4x1':0,'2x2':0} for i in range(1,5)};targets=defaultdict(list)
            for w in ws:ports[f'LP{w.load_port}'][w.mode]+=1;targets[w.load_port,w.mode].append(w.identifier)
            local=replace(cfg,load_ports=ports,chambers=(c,),pjobs=None)
            part=physical_construct(local);mapping={}
            for w in products_from_load_ports(ports):mapping[w.identifier]=targets[w.load_port,w.mode].pop(0)
            offset=len(template['pairs'])
            for p in part['pairs']:
                p=copy.deepcopy(p);p['id']+=offset;p['members']=[mapping.get(w,w) for w in p['members']];template['pairs'].append(p)
            for cy in part['cycles']:
                cy=copy.deepcopy(cy);cy['pairs']=[p+offset for p in cy['pairs']];cy['front']+=offset;template['cycles'].append(cy)
        result=physical_construct(cfg,template)
    result=normalize_schedule(cfg,result)
    from validate import validate
    result['validation']=validate(result)
    if not result['validation']['valid']:raise ValueError(result['validation']['errors'])
    return result


def constrain_seed(x,data,times=True):
    from validate import validate
    if not validate(data)['valid']:raise ValueError('Invalid qualified physical reference')
    data=normalize_schedule(x.cfg,data);m=x.model;fixed=[]
    pp={p['id']:p for p in data['pairs']};cc={(c['chamber'],c['index']):c for c in data['cycles']};ee={e['name']:e for e in data['events']}
    groups=task_for_product(x.cfg)
    if max(pp,default=-1)>=x.P or max((q for c,q in cc),default=-1)>=x.Q:raise ValueError('Reference exceeds candidate bounds')
    def eq(var,value):
        if isinstance(var,(int,float)):
            if abs(var-value)>1e-8:raise ValueError('Reference contradicts propagated constant')
        elif hasattr(var,'getLbOriginal'):
            fixed.append((var,var.getLbOriginal(),var.getUbOriginal()));m.chgVarLb(var,value);m.chgVarUb(var,value)
        else:fixed.append((None,m.addCons(var==value),None))
    for p in range(x.P):
        chosen=pp.get(p);eq(x.pair.active[p],int(chosen is not None))
        for r in (0,1):
            w=chosen['members'][r] if chosen else None
            if p<x.N:
                for g in x.groups:eq(x.pair.member[g.identifier,p,r],int(w in groups and groups[w].identifier==g.identifier))
            for t in (f'D{i+1}' for i in range(x.cfg.dummy_count)):eq(x.pair.dummy_identity[t,p,r],int(w==t))
        for mode in ('4x1','2x2','clean'):eq(x.pair.mode[p,mode],int(bool(chosen and chosen['mode']==mode)))
        for c in x.cfg.chambers:eq(x.pair.chamber[p,c],int(bool(chosen and chosen['chamber']==c)))
    for (c,q),used in x.cy.used.items():
        chosen=cc.get((c,q));eq(used,int(chosen is not None))
        if times:eq(x.cy.start[c,q],chosen['start'] if chosen else 0);eq(x.cy.end[c,q],chosen['end'] if chosen else 0)
        for p in range(x.P):eq(x.cy.occupancy[p,c,q],int(bool(chosen and p in chosen['pairs'])));eq(x.front[p,c,q],int(bool(chosen and p==chosen['front'])))
        for mode in ('4x1','2x2','clean'):eq(x.cy.kind[c,q,mode],int(bool(chosen and chosen['mode']==mode)))
    if times:
        for e in x.events:
            chosen=ee.get(e['name']);eq(e['s'],chosen['start'] if chosen else 0);eq(e['e'],chosen['end'] if chosen else 0)
        eq(x.cmax,data['cmax'])
    return fixed


def release_fixed(model,fixed):
    for var,lb,ub in fixed:
        if var is None:model.delCons(lb)
        else:model.chgVarLb(var,lb);model.chgVarUb(var,ub)
