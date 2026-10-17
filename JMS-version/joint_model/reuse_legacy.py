"""Translate frozen aggregate schedules into atomic physical events, then audit.

No search and no timestamp repair is performed. Product LP input is explicit:
legacy files do not encode individual LP origins. Default LP1 reconstruction is
therefore a declared new input instance, not an assertion about missing metadata.
"""
from pathlib import Path
from dataclasses import asdict
from collections import defaultdict
import argparse,json,re,time,copy,hashlib
from model import Config,Integrated,products_from_load_ports
from validate import validate
from seed import constrain_seed

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def convert(record,source_file,config=None):
    s=record['solution'];tol=2e-4;cycles=[]
    for k,v in s.items():
        match=re.fullmatch(r'(full_batch_used|mix_cycle_used|clean_active)_(\d+)_(\d+)',k)
        if not match or v<.5:continue
        kind,c,i=match.groups();c=int(c);i=int(i);prefix={'full_batch_used':'full','mix_cycle_used':'mix_cycle','clean_active':'clean'}[kind]
        start=s.get(f'{prefix}_start_{c}_{i}',0);end=s.get(f'{prefix}_end_{c}_{i}',0)
        if end>start+tol:cycles.append(dict(chamber=c,start=start,end=end,mode={'full':'4x1','mix_cycle':'2x2','clean':'clean'}[prefix],pairs=[]))
    for c in sorted({x['chamber'] for x in cycles}):
        count=0
        for q,cy in enumerate(sorted([x for x in cycles if x['chamber']==c],key=lambda x:x['start'])):
            count=0 if cy['mode']=='clean' else count+1;cy.update(index=q,counter=count)
    material=[]
    for typ in ('prod','pec'):
        ids=sorted({int(m.group(1)) for key in s if (m:=re.fullmatch(typ+r'_stage_end_(\d+)_vtr_unload',key)) and s[key]>tol})
        for w in ids:
            def t(edge,stage):return s.get(f'{typ}_stage_{edge}_{w}_{stage}',0.)
            times={k:(t('start',k),t('end',k)) for k in ('vtr_load','vtr_unload','pm')}
            if times['vtr_load'][1]-times['vtr_load'][0]<tol:continue
            explicit=[int(m.group(1)) for key,value in s.items() if value>.5 and (m:=re.fullmatch(fr'{typ}_job_chamber_{w}_(\d+)',key))]
            options=[]
            for c in sorted({x['chamber'] for x in cycles}):
                if explicit and c not in explicit:continue
                hits=sorted([cy for cy in cycles if cy['chamber']==c and cy['start']>=times['pm'][0]-tol and cy['end']<=times['pm'][1]+tol],key=lambda x:x['index'])
                if hits and abs(hits[0]['start']-times['pm'][0])<tol and abs(hits[-1]['end']-times['pm'][1])<tol and len({cy['mode'] for cy in hits})==1:options.append((c,hits))
            if len(options)!=1:raise ValueError(f'Ambiguous/missing chamber interval for {typ} {w}')
            c,hits=options[0];mode=hits[0]['mode']
            token=None
            if typ=='pec':
                tokens=[int(m.group(1)) for key,value in s.items() if value>.5 and (m:=re.fullmatch(fr'pec_token_assign_{w}_(\d+)',key))]
                if len(tokens)!=1:raise ValueError(f'Missing physical dummy identity for {w}')
                token=tokens[0]
            material.append(dict(old=w,typ=typ,token=token,chamber=c,mode=mode,cycles=[cy['index'] for cy in hits],times=times))
    prod=sorted([j for j in material if j['typ']=='prod'],key=lambda j:(0 if j['mode']=='4x1' else 1,j['old']))
    if config is None:
        match=re.search(r'clean0*(\d+)',record.get('instance',str(source_file)))
        if not match:raise ValueError('Cleaning interval unavailable; provide explicit config')
        lp={f'LP{i}':{} for i in range(1,5)};lp['LP1']={mode:sum(j['mode']==mode for j in prod) for mode in ('4x1','2x2')}
        config=Config(lp,cleaning_interval=int(match.group(1)))
        lp_provenance='Explicit LP1 reconstruction: legacy result has no individual LP assignment'
    else:lp_provenance='Caller-supplied load-port counts; material mapped by mode and old wafer order'
    products=products_from_load_ports(config.load_ports)
    if len(prod)!=len(products):raise ValueError('Product count mismatch')
    mapping={}
    for mode in ('4x1','2x2'):
        old=[j for j in prod if j['mode']==mode];new=[w for w in products if w.mode==mode]
        if len(old)!=len(new):raise ValueError('Recipe count mismatch')
        mapping.update({j['old']:w for j,w in zip(old,new)})
    groups=defaultdict(list)
    for j in material:
        key=(j['chamber'],j['mode'],tuple(j['cycles']),tuple(round(x,4) for t in ('vtr_load','vtr_unload') for x in j['times'][t]))
        groups[key].append(j)
    pairs=[];jobs=[];events=[];dummy_map={}
    def ev(name,kind,robot,location,start,duration,**meta):
        e=dict(name=name,kind=kind,robot=robot,location=location,start=float(start),end=float(start+duration),**meta);events.append(e);return e
    for key,members in sorted(groups.items(),key=lambda item:(item[0][3][0],item[0][0])):
        if len(members)!=2:raise ValueError('Expected two simultaneously transported members; a split legacy route needs retiming')
        members.sort(key=lambda j:(j['typ']!='prod',int(mapping[j['old']].identifier.split('_W')[1]) if j['typ']=='prod' else j['token']))
        p=len(pairs);pair=dict(id=p,chamber=key[0],mode=key[1],members=[]);pairs.append(pair)
        ls,le=members[0]['times']['vtr_load'];us,ue=members[0]['times']['vtr_unload']
        if abs(le-ls-4)>tol or abs(ue-us-4)>tol:raise ValueError('Legacy VTR duration differs from confirmed 1+2+1 seconds')
        for r,j in enumerate(members):
            w=j['old'];isprod=j['typ']=='prod'
            if isprod:identity=mapping[w].identifier;origin=f'LP{mapping[w].load_port}';name=identity
            else:
                if config.source!='dual':raise ValueError('Vacuum-source legacy dummy route cannot directly certify single-source input')
                if j['token'] not in dummy_map:dummy_map[j['token']]=f'D{len(dummy_map)+1}'
                identity=dummy_map[j['token']];origin='VS';name=f'aux_{p}_{r}'
            pair['members'].append(identity)
            jp=dict(name=name,identity=identity,product=isprod,pair=p,origin=origin,load_start=le-config.handling,load_end=le,unload_start=us,unload_end=us+config.handling)
            if isprod:
                def t(edge,stage):return s.get(f'prod_stage_{edge}_{w}_{stage}',0.)
                specs=[('origin_pick','ATR',origin,t('start','atr_lp_al')),('al_put','ATR','AL',t('start','al')-config.atr_handling),('al_pick','ATR','AL',t('end','al')),('upper_put','ATR','U',t('end','atr_al_llupper')-config.atr_handling),('lower_pick','ATR','L',t('start','atr_lllower_lp')),('origin_put','ATR',origin,t('end','atr_lllower_lp')-config.atr_handling)]
                for kind,robot,location,start in specs:ev(name+'_'+kind,kind,robot,location,start,config.atr_handling,job=name)
                jp.update(loan_start=t('start','atr_lp_al'),loan_end=t('end','atr_lllower_lp'))
            else:jp.update(loan_start=ls,loan_end=ue)
            ev(name+'_source_pick','source_pick','VTR','U' if isprod else 'VS',ls,config.handling,job=name)
            ev(name+'_destination_put','destination_put','VTR','L' if isprod else 'VS',ue-config.handling,config.handling,job=name)
            jobs.append(jp)
        ev(f'load_{p}','pair_load','VTR',f'CH{key[0]}',le-config.handling,config.handling,pair=p)
        ev(f'unload_{p}','pair_unload','VTR',f'CH{key[0]}',us,config.handling,pair=p)
        for cy in cycles:
            if cy['chamber']==key[0] and cy['index'] in key[2]:cy['pairs'].append(p)
    handling={(e['pair'],e['kind']):e for e in events if 'pair' in e}
    for c in config.chambers:
        cs=sorted([cy for cy in cycles if cy['chamber']==c],key=lambda x:x['index'])
        for q,cy in enumerate(cs):
            if len(cy['pairs'])!=2:raise ValueError('Incomplete cycle occupancy')
            front=max(cy['pairs'],key=lambda p:handling[p,'pair_load']['end']);back=next(p for p in cy['pairs'] if p!=front);cy['front']=front
            carry=set(cy['pairs'])&set(cs[q-1]['pairs']) if q else set()
            rot=cs[q-1]['end'] if carry else handling[back,'pair_load']['end']
            ev(f'rot_before_{c}_{q}','rotate',None,f'CH{c}',rot,config.rotation,chamber=c,cycle=q)
            retained=set(cy['pairs'])&set(cs[q+1]['pairs']) if q+1<len(cs) else set()
            if not retained:ev(f'rot_after_{c}_{q}','rotate',None,f'CH{c}',handling[front,'pair_unload']['end'],config.rotation,chamber=c,cycle=q)
    result=dict(schema=1,config=asdict(config),solutions=1,status='reconstructed',model_scope='joint_event_model',pairs=pairs,jobs=jobs,events=events,cycles=cycles,cmax=max(j['loan_end'] for j in jobs if j['product']),legacy_reuse=dict(source=str(Path(source_file).resolve()),source_sha256=sha(source_file),instance=record.get('instance'),lp_input_provenance=lp_provenance,wafer_mapping={str(w):v.identifier for w,v in mapping.items()},timestamps='Original stage endpoints retained; atomic VTR 1+2+1 and chamber rotation reconstructed',legacy_bound_reused=False))
    result['validation']=validate(result)
    return result

def certify(data,limit=15):
    if not data['validation']['valid']:return dict(accepted=False,reason='Independent physical replay failed')
    cfg=Config(**data['config']);cfg.max_pairs=len(data['pairs']);cfg.max_cycles=max(c['index'] for c in data['cycles'])+1
    begin=time.monotonic();x=Integrated(cfg);constrain_seed(x,data);x.model.setObjective(0,'minimize');x.model.setRealParam('limits/time',limit);x.model.optimize()
    accepted=x.model.getNSols()>0
    out=dict(accepted=accepted,status=str(x.model.getStatus()),seconds=time.monotonic()-begin,scope='Feasibility of this full event schedule only; no global lower bound',fixed_dimensions=x.original_dimensions)
    if accepted:out['replay']=validate(x.result());out['accepted']=out['replay']['valid']
    x.model.freeProb();return out

def audit(output,certify_milp=False):
    root=Path(__file__).resolve().parents[2];out=Path(output);out.mkdir(parents=True,exist_ok=True)
    sources=[root/'JMS-version/figures/temp/sources'/f'mode_n{n:03d}_clean{h:02d}_pure{mode}'/'validated_solutions.json' for n in (8,24) for h in (3,10) for mode in ('41','22')]
    sources += [root/'JMS-version/results/wafer_multiscale_gantt/gantt/wafer16_41_clean10_20260826/wafer16_41_clean10_20260826_validated_solutions.json',root/'JMS-version/results/wafer_multiscale_gantt/gantt_cycle_mapping_20260907/wafer16_22_clean10/validated_solutions.json']
    rows=[]
    for source in sources:
        started=time.monotonic();row=dict(source=str(source),accepted=False)
        try:
            record=json.loads(source.read_text(encoding='utf-8-sig'))[0];data=convert(record,source);v=data['validation'];row.update(instance=record.get('instance'),accepted=v['valid'],cmax=data['cmax'],checks=v['checks'],errors=v['errors'][:12],lp_input=data['legacy_reuse']['lp_input_provenance'])
            if certify_milp and v['valid']:row['milp']=certify(data);row['accepted']=row['milp']['accepted']
            target=out/(source.parent.name+'.json');target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');row['certificate']=str(target)
        except (ValueError,KeyError,FileNotFoundError) as exc:row['error']=str(exc)
        row['seconds']=time.monotonic()-started;rows.append(row)
    (out/'audit.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([dict(instance=r.get('instance'),accepted=r['accepted'],cmax=r.get('cmax'),errors=r.get('errors',r.get('error')),seconds=r['seconds']) for r in rows],ensure_ascii=False,indent=2))
    return rows
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--certify-milp',action='store_true');a=p.parse_args();audit(a.output,a.certify_milp)
