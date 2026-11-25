"""Native model check and publication list of the validated reverse-epsilon schedules."""
from reverse import *
from dataclasses import asdict
import hashlib
import csv
import json
import argparse
def verify_all():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    sources=list(OUT.glob('*/schedule.json'))
    pairs={s:score.metrics(b.read(s)) for s in sources}
    def priority(s):
        x=pairs[s]
        nd=not any(y['cmax']<=x['cmax']+1e-8 and y['secondary']<=x['secondary']+1e-8 and
                   (y['cmax']<x['cmax']-1e-8 or y['secondary']<x['secondary']-1e-8) for y in pairs.values())
        return (not nd,x['secondary'],x['cmax'])
    for s in sorted(sources,key=priority):
        folder=s.parent/'native'
        doc=b.read(s);f=score.metrics(doc);cfg=b.configuration()
        assert doc['config']['load_ports']==cfg.load_ports and doc['config']['cleaning_interval']==10
        rec=folder/'verification.json'
        if not rec.exists():
            _old,r=b.validate_native(cfg,doc,folder,dict(solver='CP-SAT; fixed chamber pairing, robot order free',source_sha256=b.sha(s)))
            full=b.read(folder/'schedule.json');q=score.metrics(full)
            assert all(abs(f[k]-q[k])<2e-5 for k in f)
            assert r['replay']['valid'] and r['rows']==1109436
            put(rec,dict(objective=score.OBJECTIVE,config=asdict(cfg),sha256=b.sha(folder/'schedule.json'),source=b.sha(s),
                         assignment_sha256=b.sha(folder/'assignment.json.gz'),native_rows=r['rows'],replay=r['replay'],metrics=q))
        r=b.read(rec);assert r['source']==b.sha(s) and r['sha256']==b.sha(folder/'schedule.json')
        f=r['metrics'];rows.append(dict(schedule=(folder/'schedule.json').relative_to(JMS).as_posix(),sha256=r['sha256'],
            fA=f['cmax'],fB=f['secondary'],mean_residence=f['mean_residence'],residence_range=f['residence_range'],
            clean_deficit=f['clean_deficit'],rows=r['native_rows']))
    for record in sorted((OUT/'micro').glob('*/cap_*/result.json')):
        result=b.read(record)
        if not result.get('files'):continue
        path=record.parent/'schedule.json'
        assert b.sha(path)==result['files']['schedule.json']
        assert b.sha(record.parent/'assignment.json.gz')==result['files']['assignment.json.gz']
        doc=b.read(path);f=score.metrics(doc);rp=b.validate(doc)
        assert rp['valid'] and result['original_rows']==1109436 and result['status']=='optimal'
        assert abs(f['secondary']-result['metrics']['secondary'])<2e-6 and abs(f['cmax']-rp['product_return_cmax'])<2e-6
        rows.append(dict(schedule=path.relative_to(JMS).as_posix(),sha256=b.sha(path),fA=f['cmax'],fB=f['secondary'],
                        mean_residence=f['mean_residence'],residence_range=f['residence_range'],clean_deficit=f['clean_deficit'],rows=result['original_rows']))
    family=OUT/'continuous/proof.json'
    if family.exists():
        proof=b.read(family)
        item=proof['endpoints'][-1]
        path=JMS/item['schedule']
        assert b.sha(JMS/item['assignment'])==item['assignment_sha256']
        doc=b.read(path);f=score.metrics(doc);rp=b.validate(doc)
        assert rp['valid'] and proof['max_integer_difference']==0 and proof['native_rows']==1109436
        rows.append(dict(schedule=item['schedule'],sha256=b.sha(path),fA=f['cmax'],fB=f['secondary'],
                        mean_residence=f['mean_residence'],residence_range=f['residence_range'],clean_deficit=f['clean_deficit'],rows=proof['native_rows']))
    cols=['schedule','sha256','fA','fB','mean_residence','residence_range','clean_deficit','rows']
    rows.sort(key=lambda x:(x['fA'],x['fB']))
    tmp=OUT/'candidates.csv.tmp'
    with tmp.open('w',newline='',encoding='utf8') as fp:
        f=csv.DictWriter(fp,fieldnames=cols);f.writeheader();f.writerows(rows)
    os.replace(tmp,OUT/'candidates.csv')
    put(OUT/'validation.json',dict(objective=score.OBJECTIVE,rows=rows,scope='physical feasibility independently replayed and complete native rows; non-dominance must be checked against union',H=10,n=16))
    print([(r['fA'],r['fB']) for r in rows],flush=True)
if __name__=='__main__':verify_all()
