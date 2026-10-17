"""Aggregate validated joint-model runs; never substitute fixed-layout bounds."""
from pathlib import Path
import argparse,json,csv
from collections import defaultdict
from validate import validate

def summarize(campaign):
    root=Path(campaign);manifest=json.loads((root/'campaign.json').read_text(encoding='utf-8'));rows=[];groups=defaultdict(list)
    for cell in manifest['cells']:
        run=root/'runs'/cell['id'];f=run/'result.json';cfg=json.loads((root/cell['config']).read_text(encoding='utf-8-sig'));n=sum(sum(d.values()) for d in cfg['load_ports'].values())
        modes={k for counts in cfg['load_ports'].values() for k,v in counts.items() if v};recipe=next(iter(modes)) if len(modes)==1 else 'mixed'
        row=dict(id=cell['id'],n=n,H=cfg['cleaning_interval'],source=cfg['source'],recipe=recipe,method=cell.get('method','scip'),formulation=cell.get('formulation','joint'),seed=cell['seed'],state='missing',valid=False,upper=None,lower=None,cleanings=None,variables=None,constraints=None)
        if f.exists():
            r=json.loads(f.read_text(encoding='utf-8'));v=validate(r);row.update(state=r.get('primary_status',r['status']),valid=v['valid'],lower=r.get('primary_bound'),variables=r.get('variables'),constraints=r.get('constraints'),full_space=r.get('full_candidate_space',False))
            if v['valid']:row.update(upper=v['product_return_cmax'],cleanings=v['cleaning_count'])
            if r.get('restricted_candidate_bounds'):row['lower']=None
        rows.append(row);groups[n,row['H'],row['source'],row['method'],row['formulation']].append(row)
    ranking=[]
    for key,items in groups.items():
        per_mode={}
        for mode in ('4x1','2x2','mixed'):
            rs=[r for r in items if r['recipe']==mode and r['valid']]
            per_mode[mode]=dict(upper=min((r['upper'] for r in rs if r['upper'] is not None),default=None),lower=max((r['lower'] for r in rs if r['lower'] is not None),default=None))
        eligible={k:v for k,v in per_mode.items() if v['upper'] is not None}
        best=min(eligible,key=lambda k:eligible[k]['upper']) if eligible else None
        proven=None
        if key[-1]=='joint' and len(eligible)==3:
            for mode,v in eligible.items():
                if all(other['lower'] is not None and v['upper']<other['lower']-2e-4 for k,other in eligible.items() if k!=mode):proven=mode
        ranking.append(dict(n=key[0],H=key[1],source=key[2],method=key[3],formulation=key[4],bounds=per_mode,best_observed=best,certified_unique_best=proven))
    out=root/'summary';out.mkdir(exist_ok=True)
    for name,data in [('cells',rows),('mode_ordering',ranking)]:
        (out/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'cells.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in rows))));w.writeheader();w.writerows(rows)
    return dict(expected=len(rows),completed=sum(r['state']!='missing' for r in rows),physically_valid=sum(r['valid'] for r in rows),summary=str(out))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--campaign',required=True);a=p.parse_args();print(json.dumps(summarize(a.campaign)))
