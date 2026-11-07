"""Independent physical replay plus predeclared Pjob inventory/qualification."""
from types import SimpleNamespace
from collections import defaultdict
from physical_validate import validate as physical_validate,TOL
from pjobs import task_for_product,groups_from_config


def validate(data):
    result=physical_validate(data)
    if not result['valid']:return result
    errors=result['errors'];checks=result['checks']
    def check(ok,message):
        nonlocal checks
        checks+=1
        if not ok:errors.append(message)
    try:
        cfg=SimpleNamespace(**data['config'])
        if not hasattr(cfg,'pjobs'):cfg.pjobs=None
        lookup=task_for_product(cfg);pairs={p['id']:p for p in data['pairs']}
        first={e['job']:e['start'] for e in data['events'] if e['kind']=='origin_pick'};seen=defaultdict(list)
        for j in data['jobs']:
            if not j['product']:continue
            g=lookup[j['identity']];p=pairs[j['pair']]
            check(p['chamber'] in g.chambers,'Pjob chamber qualification '+j['identity'])
            check(p['mode']==g.mode,'Pjob recipe '+j['identity'])
            if 'pjob' in j:check(j['pjob']==g.pjob,'Pjob label '+j['name'])
            r=p['members'].index(j['identity'])
            seen[g.identifier].append((first[j['name']],j['pair'],r,j['identity']))
        for g in groups_from_config(cfg):
            check([v[-1] for v in sorted(seen[g.identifier])]==list(g.labels),'Pjob canonical decoding '+g.identifier)
        for e in data['events']+data['cycles']:
            check(-TOL<=e['start'] and e['end']<=cfg.horizon+TOL,'Frozen time horizon')
    except (ValueError,KeyError,TypeError,AttributeError) as exc:errors.append('Pjob input: '+str(exc))
    return result|dict(valid=not errors,checks=checks,errors=errors,pjob_check=True)
