"""Physical schedule conversion for independently checking the Model2 preimage.

No solver module is imported, so each formulation can be checked in an isolated
Python process without mixing its module names or model objects.
"""
import copy


def to_model2(data):
    out=copy.deepcopy(data);cfg=out['config'];cfg.pop('pjobs',None)
    ids=[]
    for lp in range(1,5):
        count=sum(cfg['load_ports'][f'LP{lp}'].values())
        ids.extend(f'LP{lp}_W{slot}' for slot in range(1,count+1))
    rank={w:i for i,w in enumerate(ids)}
    pairs=sorted(out['pairs'],key=lambda p:p['id']);pairmap={p['id']:i for i,p in enumerate(pairs)}
    positions={}
    for p in pairs:
        old=p['id'];p['id']=pairmap[old]
        p['members'].sort(key=lambda w:(w not in rank,rank.get(w,0)))
        for r,w in enumerate(p['members']):positions[old,w]=r
    dummies={}
    for p in pairs:
        for w in p['members']:
            if w not in rank and w not in dummies:dummies[w]=f'D{len(dummies)+1}'
    names={}
    for j in out['jobs']:
        old=j['pair'];r=positions[old,j['identity']];j['pair']=pairmap[old]
        name=j['identity'] if j['product'] else f'aux_{j["pair"]}_{r}'
        names[j['name']]=name;j['name']=name;j['identity']=dummies.get(j['identity'],j['identity'])
        j.pop('pjob',None);j.pop('wafer_number',None)
    for p in pairs:p['members']=[dummies.get(w,w) for w in p['members']]
    for e in out['events']:
        if 'job' in e:e['job']=names[e['job']];e['name']=e['job']+'_'+e['kind']
        if 'pair' in e:e['pair']=pairmap[e['pair']];e['name']=('load_' if e['kind']=='pair_load' else 'unload_')+str(e['pair'])
    for c in out['cycles']:c['pairs']=[pairmap[p] for p in c['pairs']];c['front']=pairmap[c['front']]
    out['pairs']=pairs;out['model_scope']='physical_preimage_for_model2_check'
    out.pop('validation',None)
    return out
