"""Conservative retry gate; a failed budget is not a minimum-memory theorem."""
from pathlib import Path
import json,hashlib

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def canonical(value):return json.dumps(value,sort_keys=True)

def require_unfailed_budget(history,cases,assets,settings,memory_mb):
    hits=[]
    for campaign in sorted(Path(history).glob('supp_*')):
        if not (campaign/'campaign.json').exists():continue
        spec=read(campaign/'campaign.json')
        if spec.get('assets')!=assets:continue
        if any(spec.get(k)!=settings[k] for k in ('time_limit','wall_limit','spbs_budget')):continue
        if spec.get('memory_mb',0)<memory_mb:continue
        for failpath in sorted((campaign/'preflight_logs').glob('*.failure.json')):
            key=failpath.name.removesuffix('.failure.json')
            if key not in cases:continue
            cfg=campaign/'configs'/f'{key}.json'
            if not cfg.exists() or hashlib.sha256(cfg.read_bytes()).hexdigest()!=spec.get('case_hashes',{}).get(key):continue
            if canonical(read(cfg))!=canonical(cases[key]):continue
            fail=read(failpath);reason=fail.get('reason');confirmed=reason=='process_memory_guard'
            if reason=='exit_1':
                log=Path(fail.get('log','')).resolve()
                if log.is_relative_to((campaign/'preflight_logs').resolve()) and log.is_file():
                    confirmed='Common start completion failed: memlimit' in log.read_text(encoding='utf-8',errors='replace')
            if confirmed:hits.append((spec['memory_mb'],key,failpath))
    if hits:
        budget,key,path=max(hits,key=lambda h:h[0])
        raise RuntimeError(f'Known reference memory failure for {key} at {budget} MiB; requested {memory_mb} MiB is not higher. '
            f'No reference or solver started. Changing directory cannot resolve this. Preserve {path}. '
            'Use an evaluated higher-memory protocol or validated model changes; more RAM alone does not guarantee success.')
