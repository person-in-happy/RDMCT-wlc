"""Immutable task input and lossless product-label decoding for Model4."""
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductWafer:
    identifier: str
    load_port: int
    mode: str


@dataclass(frozen=True)
class Group:
    identifier: str
    pjob: str
    load_port: int
    mode: str
    chambers: tuple
    labels: tuple

    @property
    def count(self):
        return len(self.labels)


def products_from_load_ports(load_ports):
    if set(load_ports) != {f'LP{i}' for i in range(1,5)}:
        raise ValueError('Specify LP1--LP4 including empty ports')
    result=[]
    for lp in range(1,5):
        counts=load_ports[f'LP{lp}']; slot=0
        if set(counts)-{'4x1','2x2'}:
            raise ValueError('Unknown recipe')
        for mode in ('4x1','2x2'):
            count=counts.get(mode,0)
            if type(count) is not int or count<0:
                raise ValueError('Inventory must be nonnegative integers')
            for _ in range(count):
                slot+=1;result.append(ProductWafer(f'LP{lp}_W{slot}',lp,mode))
        if slot>25:
            raise ValueError('LP capacity exceeds 25')
    return tuple(result)


def groups_from_config(cfg):
    products=products_from_load_ports(cfg.load_ports)
    if not cfg.chambers or len(set(cfg.chambers))!=len(cfg.chambers) or any(type(c) is not int or c<1 for c in cfg.chambers):
        raise ValueError('Chambers must be distinct positive integer labels')
    # Mode/LP counts in the legacy input already aggregate inventory. Explicit
    # Pjobs supply the additional predeclared qualification and output ID list.
    tasks=cfg.pjobs
    if tasks is None:
        tasks=[dict(id=f'Pjob{i+1}',mode=mode,chambers=list(cfg.chambers),
                    wafers=[w.identifier for w in products if w.mode==mode])
               for i,mode in enumerate(m for m in ('4x1','2x2') if any(w.mode==m for w in products))]
    if not isinstance(tasks,list) or not tasks:
        raise ValueError('Nonempty Pjob input required')
    byid={w.identifier:w for w in products};seen=set();ids=set();attributes=set();groups=[]
    for task in tasks:
        if set(task)!={'id','mode','chambers','wafers'}:
            raise ValueError('Pjob fields: id, mode, chambers, wafers')
        name=task['id']; mode=task['mode']; chambers=tuple(sorted(set(task['chambers'])))
        if not isinstance(name,str) or not name.startswith('Pjob') or not name.replace('_','').isalnum() or name in ids:
            raise ValueError('Unique alphanumeric Pjob IDs required')
        if mode not in ('4x1','2x2') or not chambers or not set(chambers)<=set(cfg.chambers):
            raise ValueError('Unknown recipe or empty/unknown chamber qualification')
        if (mode,chambers) in attributes:
            raise ValueError('Merge identical recipe/qualification tasks; LP inventory stays separate')
        attributes.add((mode,chambers));ids.add(name);ports=defaultdict(list)
        if not isinstance(task['wafers'],list) or not task['wafers']:
            raise ValueError('Empty Pjob')
        for label in task['wafers']:
            if label not in byid or label in seen or byid[label].mode!=mode:
                raise ValueError('Pjob IDs must cover each product once with its input recipe')
            seen.add(label);ports[byid[label].load_port].append(label)
        for lp,labels in sorted(ports.items()):
            labels.sort(key=lambda w:int(w.split('_W')[1]))
            groups.append(Group(f'{name}_LP{lp}',name,lp,mode,chambers,tuple(labels)))
    if seen!=set(byid):
        raise ValueError('Pjob inventory does not cover all products')
    return tuple(sorted(groups,key=lambda g:(g.pjob,g.load_port)))


def task_for_product(cfg):
    return {w:g for g in groups_from_config(cfg) for w in g.labels}


def with_qualification_profile(cfg,profile):
    from dataclasses import replace
    if profile not in ('all','three_classes','lp_split'):raise ValueError('Unknown qualification profile')
    if profile=='all':return cfg
    if len(cfg.chambers)!=2:raise ValueError('Qualification profiles require exactly two chambers')
    first,second=cfg.chambers;bins=defaultdict(list)
    for mode in ('4x1','2x2'):
        ws=[w for w in products_from_load_ports(cfg.load_ports) if w.mode==mode]
        for i,w in enumerate(ws):
            kind=i%3 if profile=='three_classes' else 0 if w.load_port==1 else 1 if w.load_port==2 else 2
            allowed=(first,) if kind==0 else (second,) if kind==1 else tuple(sorted(cfg.chambers))
            bins[mode,allowed].append(w.identifier)
    tasks=[dict(id=f'Pjob{i+1}',mode=key[0],chambers=list(key[1]),wafers=labels) for i,(key,labels) in enumerate(sorted(bins.items()))]
    return replace(cfg,pjobs=tasks)
