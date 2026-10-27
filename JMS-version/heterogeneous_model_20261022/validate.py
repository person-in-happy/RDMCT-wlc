"""Independent physical replay. Uses exported times, never SCIP constraints."""
from collections import Counter,defaultdict
from itertools import combinations
import math

TOL=2e-4

def validate(data):
    errors=[];checks=0
    def check(ok,msg):
        nonlocal checks
        checks+=1
        if not ok:errors.append(msg)
    if not data.get('solutions'):return {'valid':False,'checks':0,'errors':['No incumbent schedule']}
    cfg=data['config'];events=data['events'];pairs={p['id']:p for p in data['pairs']};jobs={j['name']:j for j in data['jobs']}
    product={}
    for lp,counts in cfg['load_ports'].items():
        i=0
        for mode in ('4x1','2x2'):
            for _ in range(counts.get(mode,0)):
                i+=1;product[f'{lp}_W{i}']=(mode,lp)
    # Validate schema separately from the optimization model; cycle durations
    # below are derived directly from exported physical product identities.
    from types import SimpleNamespace
    from recipes import validate_groups
    from joint_pairing_model import products_from_load_ports
    try:
        validate_groups(SimpleNamespace(**dict(cfg,processing_groups=cfg.get('processing_groups',{}))),products_from_load_ports(cfg['load_ports']))
    except (ValueError,TypeError,KeyError) as exc:
        return {'valid':False,'checks':checks,'errors':['Processing-group schema: '+str(exc)]}
    wafer_group={w:g for g,spec in cfg.get('processing_groups',{}).items() for w in spec['wafers']}
    check(len(pairs)==len(data['pairs']),'Duplicate pair IDs')
    check(len(jobs)==len(data['jobs']),'Duplicate job IDs')
    check(set(j['identity'] for j in jobs.values() if j['product'])==set(product),'Product identity coverage')
    check(Counter(j['identity'] for j in jobs.values() if j['product'])==Counter({w:1 for w in product}),'Each product exactly once')
    check(Counter(w for p in pairs.values() for w in p['members'] if w in product)==Counter({w:1 for w in product}),'Pair membership coverage')
    byjob=defaultdict(dict);bypair=defaultdict(dict);bych=defaultdict(list)
    for e in events:
        check(all(math.isfinite(e[k]) for k in ('start','end')),'Nonfinite event')
        check(e['start']>=-TOL and e['end']>=e['start']-TOL,f"Negative time {e['name']}")
        expected=cfg['rotation'] if e['kind']=='rotate' else cfg['atr_handling'] if e['robot']=='ATR' else cfg['handling']
        check(abs(e['end']-e['start']-expected)<TOL,f"Duration {e['name']}")
        if 'job' in e:byjob[e['job']][e['kind']]=e
        if 'pair' in e:bypair[e['pair']][e['kind']]=e
        if e['location'].startswith('CH'):bych[int(e['location'][2:])].append(e)
    def cap(intervals,capacity,name):
        # Values are rounded only to merge solver tolerances at common boundaries.
        timeline=defaultdict(int)
        for start,end,key in intervals:
            check(end>=start-TOL,f'{name} negative occupancy {key}')
            if end-start>TOL:timeline[round(start,4)]+=1;timeline[round(end,4)]-=1
        count=0
        for t,change in sorted(timeline.items()):
            count+=change;check(0<=count<=capacity,f'{name} capacity at {t}: {count}>{capacity}')
    def before(a,b,msg):check(a<=b+TOL,msg)
    resources=defaultdict(list);loans=defaultdict(list)
    for p in pairs.values():
        check(len(p['members'])==2 and len(set(p['members']))==2,f"Pair {p['id']} member count")
        check(p['chamber'] in cfg['chambers'],f"Pair {p['id']} chamber")
        for w in p['members']:
            check(w in product or w in {f'D{i+1}' for i in range(cfg['dummy_count'])},f'Unknown wafer {w}')
            if w in product:check(product[w][0]==p['mode'],f'Mode compatibility {w}')
        pp=bypair[p['id']]
        check(set(pp)=={'pair_load','pair_unload'},f"Missing chamber handling {p['id']}")
        if len(pp)!=2:continue
        for e in pp.values():check(e['location']==f"CH{p['chamber']}",f"Chamber link {p['id']}")
        before(pp['pair_load']['end'],pp['pair_unload']['start'],'Pair residence order')
        check(pp['pair_unload']['start']-pp['pair_load']['end']<=cfg['module_residency']+TOL,'Chamber residency')
        matched=[j for j in jobs.values() if j['pair']==p['id']]
        check(Counter(j['identity'] for j in matched)==Counter(p['members']),f"Physical jobs in pair {p['id']}")
    for name,j in jobs.items():
        e=byjob[name];p=pairs[j['pair']];pp=bypair[j['pair']]
        expected_origin=product[j['identity']][1] if j['product'] else ('AS' if cfg['source']=='single' else 'VS')
        check(j['origin']==expected_origin,f'Source route {name}')
        atmospheric=expected_origin!='VS'
        align=j['product'] or cfg.get('dummy_alignment','legacy_align_all')=='legacy_align_all'
        kinds=['origin_pick','al_put','al_pick','upper_put','source_pick','destination_put','lower_pick','origin_put'] if atmospheric else ['source_pick','destination_put']
        if atmospheric and not align:kinds=[k for k in kinds if k not in ('al_put','al_pick')]
        check(set(e)==set(kinds),f'Route event coverage {name}')
        if not set(kinds)<=set(e):continue
        locs={'origin_pick':expected_origin,'al_put':'AL','al_pick':'AL','upper_put':'U','source_pick':'U' if atmospheric else 'VS','destination_put':'L' if atmospheric else 'VS','lower_pick':'L','origin_put':expected_origin}
        for k in kinds:check(e[k]['location']==locs[k],f'Route location {name}:{k}')
        for k,pk in [('load','pair_load'),('unload','pair_unload')]:
            for side in ('start','end'):check(abs(j[k+'_'+side]-pp[pk][side])<TOL,f'Job/chamber timing {name}')
        legs=[(e['source_pick']['end']+cfg['vtr_travel'],j['load_start']),(j['unload_end']+cfg['vtr_travel'],e['destination_put']['start'])]
        resources['VTR'].extend([(e['source_pick']['start'],j['load_end'],name),(j['unload_start'],e['destination_put']['end'],name)])
        if atmospheric:
            entry=[('origin_pick','al_put',cfg['atr_travel']),('al_put','al_pick',cfg['alignment']),('al_pick','upper_put',cfg['atr_travel'])] if align else [('origin_pick','upper_put',cfg['atr_travel'])]
            for a,b,d in entry+[('upper_put','source_pick',cfg['pump']),('destination_put','lower_pick',cfg['vent']),('lower_pick','origin_put',cfg['atr_travel'])]:legs.append((e[a]['end']+d,e[b]['start']))
            if align:
                resources['ATR'].extend([(e['origin_pick']['start'],e['al_put']['end'],name),(e['al_pick']['start'],e['upper_put']['end'],name)])
                resources['AL'].append((e['al_put']['start'],e['al_pick']['end'],name))
                check(e['al_pick']['start']-e['al_put']['end']<=cfg['module_residency']+TOL,f'Module residency {name}')
            else:
                resources['ATR'].append((e['origin_pick']['start'],e['upper_put']['end'],name))
                partner=next((jj for jj in jobs.values() if jj['pair']==j['pair'] and jj['product']),None)
                if partner:
                    pe=byjob[partner['name']]
                    if 'al_put' in pe and 'upper_put' in pe:
                        early=e['upper_put']['end']<=pe['al_put']['start']+TOL
                        late=e['origin_pick']['start']>=pe['al_put']['end']-TOL
                        escort=e['origin_pick']['end']<=pe['al_put']['start']+TOL and all(abs(e['upper_put'][k]-pe['upper_put'][k])<=TOL for k in ('start','end'))
                        check(early or late or escort,f'Dummy accompanies product through AL and common LL placement {name}')
            resources['ATR'].append((e['lower_pick']['start'],e['origin_put']['end'],name))
            resources['U'].append((e['upper_put']['start'],e['source_pick']['end']+cfg['upper_reset'],name))
            resources['L'].append((e['destination_put']['start'],e['lower_pick']['end']+cfg['lower_reset'],name))
            for a,b in [('upper_put','source_pick'),('destination_put','lower_pick')]:check(e[b]['start']-e[a]['end']<=cfg['module_residency']+TOL,f'Module residency {name}')
        for a,b in legs:before(a,b,f'Route precedence {name}')
        check(abs(j['loan_start']-e[kinds[0]]['start'])<TOL and abs(j['loan_end']-e[kinds[-1]]['end'])<TOL,f'Complete material loan {name}')
        if not j['product']:loans[j['identity']].append((j['loan_start'],j['loan_end'],name))
    for r,items in resources.items():
        cap(items,{'VTR':4,'ATR':2,'AL':1,'U':2,'L':2}[r],r)
        if r in ('ATR','VTR'):
            for a,b,name in items:check(b-a<=cfg['robot_residency']+TOL,f'Robot residency {name}')
    policy=cfg.get('vtr_hand_policy','legacy_unrestricted')
    check(policy in ('clean_dirty','legacy_unrestricted'),'Unknown VTR hand policy')
    if policy=='clean_dirty':
        from grippers import HANDS
        hand_use=defaultdict(list)
        for name,j in jobs.items():
            e=byjob[name]
            if not {'source_pick','destination_put'}<=set(e):continue
            for leg,start,end in [('in',e['source_pick']['start'],j['load_end']),('out',j['unload_start'],e['destination_put']['end'])]:
                hand=j.get('vtr_hand_'+leg)
                allowed=HANDS[:2] if j['product'] and leg=='in' else HANDS[2:] if j['product'] else HANDS
                check(hand in allowed,f'VTR hand eligibility {name}:{leg}: {hand}')
                if hand in HANDS:hand_use[hand].append((start,end,name+'_'+leg))
        for hand,items in hand_use.items():cap(items,1,'VTR hand '+hand)
    for d,items in loans.items():cap(items,1,d)
    for robot in ('ATR','VTR'):
        es=[e for e in events if e['robot']==robot]
        for a,b in combinations(es,2):
            if a['end']<=b['start']+TOL:earlier,later=a,b
            elif b['end']<=a['start']+TOL:earlier,later=b,a
            else:
                sync=('job' in a and 'job' in b and a['job']!=b['job'] and jobs[a['job']]['pair']==jobs[b['job']]['pair'] and a['kind']==b['kind'] and a['kind'] not in ('al_put','al_pick') and a['location']==b['location'] and abs(a['start']-b['start'])<TOL and abs(a['end']-b['end'])<TOL)
                check(sync,f'Robot overlap {a["name"]}/{b["name"]}');continue
            travel=0 if earlier['location']==later['location'] or {earlier['location'],later['location']}<={'U','L'} else cfg['atr_travel' if robot=='ATR' else 'vtr_travel']
            if robot=='ATR' and earlier['location'] in ('U','L') and (later['location'].startswith('LP') or later['location']=='AS') and later['kind']=='origin_pick':travel=cfg['atr_empty_ll_to_lp']
            before(earlier['end']+travel,later['start'],f'Robot travel {earlier["name"]}/{later["name"]}')
    occurrences=defaultdict(list)
    for c in cfg['chambers']:
        cycles=sorted([x for x in data['cycles'] if x['chamber']==c],key=lambda x:x['index'])
        check([x['index'] for x in cycles]==list(range(len(cycles))),f'Cycle prefix CH{c}')
        counter=0;ops=list(bych[c])
        for i,cy in enumerate(cycles):
            expected={'4x1':cfg['full_time'],'2x2':cfg['mix_time'],'clean':cfg['cleaning_time']}[cy['mode']]
            if wafer_group and cy['mode']!='clean':
                gs={wafer_group[w] for p in cy['pairs'] if p in pairs for w in pairs[p]['members'] if w in product}
                check(len(gs)==1,f'Processing-group compatibility CH{c}:{i}')
                if len(gs)==1:expected=cfg['processing_groups'][next(iter(gs))][cy['mode']]
            check(abs(cy['end']-cy['start']-expected)<TOL,f'Exposure duration CH{c}:{i}')
            ids=cy['pairs'];check(len(ids)==2 and len(set(ids))==2,f'Four-pocket occupancy CH{c}:{i}')
            if len(ids)!=2:continue
            ws=[w for p in ids for w in pairs[p]['members']]
            check(len(ws)==len(set(ws))==4,f'Four distinct wafers CH{c}:{i}')
            for p in ids:
                occurrences[p].append((c,i));check(pairs[p]['chamber']==c and pairs[p]['mode']==cy['mode'],f'Cycle compatibility CH{c}:{i}')
                before(bypair[p]['pair_load']['end'],cy['start'],'Load before exposure');before(cy['end'],bypair[p]['pair_unload']['start'],'Exposure before unload')
            if cy['mode']=='clean':
                check(not any(w in product for w in ws),'Products in cleaning')
                check(1<=counter<=cfg['cleaning_interval'],f'Cleaning trigger CH{c}:{i}');counter=0
            else:
                check(any(w in product for w in ws),'Product-free productive cycle');counter+=1
            check(counter<=cfg['cleaning_interval'],f'Cleaning threshold CH{c}:{i}')
            check(abs(counter-cy['counter'])<TOL,f'Cleaning counter CH{c}:{i}')
            ops.append(dict(name=f'exposure_{c}_{i}',kind='exposure',start=cy['start'],end=cy['end'],pairs=ids,front=cy['front']))
        check(counter<cfg['cleaning_interval'],f'Missing terminal cleaning CH{c}')
        ops.sort(key=lambda x:(x['start'],x['end']))
        front=back=None;last_end=0
        for op in ops:
            before(last_end,op['start'],f'Chamber overlap CH{c}:{op["name"]}');last_end=op['end']
            if op['kind']=='pair_load':check(front is None,f'Loading occupied front CH{c}');front=op['pair']
            elif op['kind']=='pair_unload':check(front==op['pair'],f'Unload wrong side CH{c}');front=None
            elif op['kind']=='rotate':front,back=back,front
            elif op['kind']=='exposure':check(front==op['front'] and {front,back}==set(op['pairs']),f'Exposure orientation CH{c}')
        check(front is None and back is None,f'Incomplete chamber unload CH{c}')
    for p in pairs.values():
        occ=occurrences[p['id']];n=2 if p['mode']=='2x2' and any(w in product for w in p['members']) else 1
        check(len(occ)==n,f'Exposure count pair {p["id"]}')
        if n==2 and len(occ)==2:check(occ[0][0]==occ[1][0] and occ[1][1]==occ[0][1]+1,f'Consecutive exposures {p["id"]}')
    finish=max((j['loan_end'] for j in jobs.values() if j['product']),default=0)
    check(finish<=data['cmax']+TOL,'Product makespan bound')
    return {'valid':not errors,'checks':checks,'errors':errors,'product_return_cmax':finish,'cleaning_count':sum(x['mode']=='clean' for x in data['cycles']),'processing_cycles':sum(x['mode']!='clean' for x in data['cycles'])}
