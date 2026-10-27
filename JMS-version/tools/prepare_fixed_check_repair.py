"""Freeze an isolated replay of failed fixed checks with identical saved starts."""
from pathlib import Path
from types import SimpleNamespace
import argparse
import hashlib
import json
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import evidence_supplement as e


def prepare(source, output):
    source=e.campaign_path(source);out=e.campaign_path(output)
    if source==out or out.exists():
        raise ValueError('Repair requires a NEW directory; use Run/Resume for an already prepared repair')
    old=e.read(source/'campaign.json');meta=e.read(source/'supplement.json')
    if e.digest(source/'campaign.json')!=meta['campaign_sha256']:
        raise RuntimeError('Source manifest changed')
    if old['suite']!='fixed':raise ValueError('Expected the fixed supplement')
    changed={name for name,sha in old['assets'].items() if e.digest(e.ROOT/name)!=sha}
    if changed!={str(Path('JMS-version/joint_model/run_experiments.py'))}:
        raise RuntimeError('Expected only the diagnosed check-scope fix; changed assets: '+str(changed))
    cells=[];provenance={}
    for cell in old['cells']:
        dest=source/'runs'/cell['id']
        if not (dest/'failure.json').exists():continue
        result=e.read(dest/'result.json')
        if (cell['variant']!='fixed' or result['original_model_check'] is not False or
                not e.validate(result)['valid'] or not result['solutions']):
            raise RuntimeError('Failure is outside this check-scope repair: '+cell['id'])
        manifest=e.read(dest/'manifest.json')
        if e.digest(dest/'model.lp.gz')!=manifest['lp_sha256']:
            raise RuntimeError('Source model changed')
        ref=source/'references'/cell['case']
        e.reference_receipt(source,cell['case'],old)
        if manifest['fixed_reference_sha256']!=e.digest(ref/'reference.json'):
            raise RuntimeError('Source fixed structure changed')
        if manifest['warm_start_sha256']!=e.digest(ref/'common.json'):
            raise RuntimeError('Source warm assignment changed')
        cells.append(cell)
        provenance[cell['id']]={name:e.digest(dest/name) for name in
                               ('result.json','failure.json','variables.json','model.lp.gz','manifest.json')}
    if not cells:raise RuntimeError('No eligible failed fixed cells')
    resources=meta['contract']['settings']
    if any(resources[k]!=e.defaults('fixed')[k] for k in ('time_limit','wall_limit','spbs_budget')):
        raise RuntimeError('Unexpected original budget; register a separate repair protocol')
    e.prepare(SimpleNamespace(campaign=str(out),suite='fixed',memory_mb=resources['memory_mb'],jobs=resources['jobs']))
    spec=e.read(out/'campaign.json');newmeta=e.read(out/'supplement.json')
    for key in {c['case'] for c in cells}:
        if e.digest(out/'configs'/(key+'.json'))!=old['case_hashes'][key]:
            raise RuntimeError('Repair input differs from source')
        shutil.copytree(source/'references'/key,out/'references'/key)
    spec['cells']=cells;spec['seeds']=sorted({c['seed'] for c in cells})
    spec['case_hashes']={k:v for k,v in spec['case_hashes'].items() if k in {c['case'] for c in cells}}
    spec['repair_provenance']=dict(source=str(source),source_campaign_sha256=e.digest(source/'campaign.json'),
        source_finished_sha256=e.digest(source/'finished.json'),source_cells=provenance,
        changed_assets=sorted(changed),preparation_sha256=e.digest(Path(__file__)),
        scope='Validation-scope repair, separate runs; historical failures retained; no new independent instances',
        initialization='Byte-identical certified references and common assignments copied from source')
    newmeta['contract']['settings']['seeds']=spec['seeds']
    e.dump(out/'campaign.json',spec)
    newmeta['campaign_sha256']=e.digest(out/'campaign.json');e.dump(out/'supplement.json',newmeta)
    snapshot=out/'frozen_code'/Path(__file__).relative_to(e.ROOT)
    snapshot.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(Path(__file__),snapshot)
    e.checked(out)
    print(json.dumps(dict(output=str(out),repair_cells=[c['id'] for c in cells],
        next='Preflight then Run; same directory for Resume; no historical status was rewritten')))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();prepare(a.source,a.output)
