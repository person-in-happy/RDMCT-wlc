"""Canonical labels only: members, chambers, cycle positions stay decisions."""
import copy,re


def canonical_seed(data,product_ids):
    result=copy.deepcopy(data);products=set(product_ids);index={w:i for i,w in enumerate(product_ids)}
    first={}
    for c in data['cycles']:
        for p in c['pairs']:first[p]=min(first.get(p,(10**9,10**9)),(c['chamber'],c['index']))
    def key(p):
        pw=[w for w in p['members'] if w in products]
        rank=0 if pw else (2 if p['mode']=='clean' else 1)
        return rank,(min(index[w] for w in pw) if pw else first[p['id']]),p['id']
    ordered=sorted(result['pairs'],key=key);mapping={p['id']:i for i,p in enumerate(ordered)};dummies={}
    for p in ordered:
        for w in p['members']:
            if w not in products and w not in dummies:dummies[w]='D'+str(len(dummies)+1)
    def rename(name):
        name=re.sub(r'^aux_(\d+)_(\d+)(.*)$',lambda m:f'aux_{mapping[int(m[1])]}_{m[2]}{m[3]}',name)
        return re.sub(r'^(load|unload)_(\d+)$',lambda m:f'{m[1]}_{mapping[int(m[2])]}',name)
    for p in ordered:
        p['id']=mapping[p['id']];p['members']=[dummies.get(w,w) for w in p['members']]
    result['pairs']=ordered
    for c in result['cycles']:
        c['pairs']=[mapping[p] for p in c['pairs']];c['front']=mapping[c['front']]
    for e in result['events']:
        e['name']=rename(e['name'])
        if 'job' in e:e['job']=rename(e['job'])
        if 'pair' in e:e['pair']=mapping[e['pair']]
    for j in result['jobs']:
        j['name']=rename(j['name']);j['pair']=mapping[j['pair']];j['identity']=dummies.get(j['identity'],j['identity'])
    return result,dict(pair_labels=mapping,dummy_labels=dummies)


def add_label_symmetry(x):
    m=x.model;pair=x.pair;has=x.cy.product_pair;n=len(x.products)
    ranks=[3-pair.active[p]-has[p]-pair.mode[p,'4x1']-pair.mode[p,'2x2'] for p in range(x.P)]
    productkeys=[sum((i+1)*pair.member[w.identifier,p,0] for i,w in enumerate(x.products)) for p in range(x.P)]
    firstkeys=[sum((ci*x.Q+q+1)*x.cy.first[p,c,q] for ci,c in enumerate(x.cfg.chambers) for q in range(x.Q)) for p in range(x.P)]
    for p in range(x.P-1):
        m.addCons(ranks[p]<=ranks[p+1])
        m.addCons(productkeys[p]<=productkeys[p+1]+(n+1)*(2-has[p]-has[p+1]))
        a=pair.mode[p,'4x1']+pair.mode[p,'2x2']-has[p]
        b=pair.mode[p+1,'4x1']+pair.mode[p+1,'2x2']-has[p+1]
        support=x.and_(a,b,f'label_support_neighbors_{p}')
        clean=x.and_(pair.mode[p,'clean'],pair.mode[p+1,'clean'],f'label_clean_neighbors_{p}')
        for active in (support,clean):m.addCons(firstkeys[p]<=firstkeys[p+1]+(len(x.cfg.chambers)*x.Q+1)*(1-active))
    return dict(theorem='anonymous_pair_and_dummy_label_permutation_v1',
                order='product pairs by first member, support pairs by first cycle, cleaning pairs by first cycle, inactive pairs')
