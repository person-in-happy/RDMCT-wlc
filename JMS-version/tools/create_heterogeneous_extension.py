"""Create an isolated fork; never overwrite an existing fork or shared source."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'JMS-version/heterogeneous_model_20261022'

def main():
    DEST.mkdir(exist_ok=False)
    sources=[ROOT/'JMS-version/joint_model'/n for n in ('model.py','seed.py','validate.py','grippers.py')]
    sources += [ROOT/n for n in ('joint_pairing_model.py','joint_chamber_cycle_model.py','scip_imports.py','runtime_compat.py')]
    manifest={}
    for src in sources:
        raw=src.read_bytes();(DEST/src.name).write_bytes(raw)
        manifest[str(src.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest()
    (DEST/'base_sources.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    def edit(name,old,new):
        p=DEST/name;s=p.read_text(encoding='utf-8')
        if s.count(old)!=1:raise ValueError((name,'Expected exactly one replacement',old))
        p.write_text(s.replace(old,new),encoding='utf-8')
    edit('model.py','from dataclasses import dataclass, asdict','from dataclasses import dataclass, asdict, field')
    edit('model.py','ROOT=Path(__file__).resolve().parents[2]','ROOT=Path(__file__).resolve().parent')
    edit('model.py','    source: str=\'dual\'','    processing_groups: dict=field(default_factory=dict)\n    source: str=\'dual\'')
    edit('model.py','        self.products=products_from_load_ports(cfg.load_ports)',
         '        self.products=products_from_load_ports(cfg.load_ports)\n        from recipes import validate_groups\n        self.wafer_groups=validate_groups(cfg, self.products)')
    edit('model.py',"durations={'4x1':cfg.full_time,'2x2':cfg.mix_time,'clean':cfg.cleaning_time},horizon=self.H)",
         "durations={'4x1':cfg.full_time,'2x2':cfg.mix_time,'clean':cfg.cleaning_time},horizon=self.H,\n             processing_groups=cfg.processing_groups)")
    edit('joint_chamber_cycle_model.py','                       durations, horizon):','                       durations, horizon, processing_groups=None):')
    edit('joint_chamber_cycle_model.py','    H=cleaning_interval', '''    # Every product pair and productive cycle selects one recipe group.
    # Dummy-only support pairs inherit no group and may support any one group.
    groups=processing_groups or {}
    pg={(p,g):B(f'hg_pair_{p}_{g}') for p in P for g in groups}
    cg={(c,q,g,k):B(f'hg_cycle_{c}_{q}_{g}_{k}') for c in C for q in Q for g in groups for k in ('4x1','2x2')}
    if groups:
        for p in P:
            model.addCons(scip.quicksum(pg[p,g] for g in groups)==has[p])
            for g,spec in groups.items():
                members=scip.quicksum(pairing.member[w,p,r] for w in spec['wafers'] for r in (0,1))
                model.addCons(members>=pg[p,g]);model.addCons(members<=2*pg[p,g])
        for c in C:
            for q in Q:
                for k in ('4x1','2x2'):
                    model.addCons(scip.quicksum(cg[c,q,g,k] for g in groups)==kind[c,q,k])
                for p in P:
                    for g in groups:
                        model.addCons(occ[p,c,q]+pg[p,g]<=1+cg[c,q,g,'4x1']+cg[c,q,g,'2x2'])
    H=cleaning_interval''')
    edit('joint_chamber_cycle_model.py',"            model.addCons(ends[c,q]==starts[c,q]+scip.quicksum(durations[m]*kind[c,q,m] for m in M))",'''            duration=(durations['clean']*kind[c,q,'clean']+scip.quicksum(
                groups[g][k]*cg[c,q,g,k] for g in groups for k in ('4x1','2x2'))
                if groups else scip.quicksum(durations[m]*kind[c,q,m] for m in M))
            model.addCons(ends[c,q]==starts[c,q]+duration)''')
    edit('seed.py','    products=products_from_load_ports(cfg.load_ports);byid={w.identifier:w for w in products}',
         '    products=products_from_load_ports(cfg.load_ports);byid={w.identifier:w for w in products}\n    from recipes import validate_groups\n    wafer_groups=validate_groups(cfg,products)')
    edit('seed.py',"        counter=0 if mode=='clean' else counter+1",'''        if cfg.processing_groups and mode!='clean':
            gs={wafer_groups[w] for p in (back,front) for w in pairs[p]['members'] if w in byid}
            if len(gs)!=1:raise ValueError('Incompatible processing groups in seed cycle')
            duration=cfg.processing_groups[next(iter(gs))][mode]
        counter=0 if mode=='clean' else counter+1''')
    start="        groups={k:[] for k in ('4x1','2x2')}"
    end="    result=dict(schema=1,config=asdict(cfg)"
    p=DEST/'seed.py';s=p.read_text(encoding='utf-8');i=s.index(start);j=s.index(end,i)
    block=s[i:j]
    block=block.replace('w.mode==mode','w.mode==mode and (not cfg.processing_groups or wafer_groups[w.identifier]==group)')
    block='        for group in (list(cfg.processing_groups) or [None]):\n'+''.join('    '+line+'\n' for line in block.splitlines())
    p.write_text(s[:i]+block+s[j:],encoding='utf-8')
    edit('validate.py',"    check(len(pairs)==len(data['pairs']),'Duplicate pair IDs')",'''    # Validate schema separately from the optimization model; cycle durations
    # below are derived directly from exported physical product identities.
    from types import SimpleNamespace
    from recipes import validate_groups
    from joint_pairing_model import products_from_load_ports
    try:
        validate_groups(SimpleNamespace(**dict(cfg,processing_groups=cfg.get('processing_groups',{}))),products_from_load_ports(cfg['load_ports']))
    except (ValueError,TypeError,KeyError) as exc:
        return {'valid':False,'checks':checks,'errors':['Processing-group schema: '+str(exc)]}
    wafer_group={w:g for g,spec in cfg.get('processing_groups',{}).items() for w in spec['wafers']}
    check(len(pairs)==len(data['pairs']),'Duplicate pair IDs')''')
    edit('validate.py',"            check(abs(cy['end']-cy['start']-expected)<TOL,f'Exposure duration CH{c}:{i}')",'''            if wafer_group and cy['mode']!='clean':
                gs={wafer_group[w] for p in cy['pairs'] if p in pairs for w in pairs[p]['members'] if w in product}
                check(len(gs)==1,f'Processing-group compatibility CH{c}:{i}')
                if len(gs)==1:expected=cfg['processing_groups'][next(iter(gs))][cy['mode']]
            check(abs(cy['end']-cy['start']-expected)<TOL,f'Exposure duration CH{c}:{i}')''')
    print(DEST)

if __name__=='__main__':main()
