"""Verify evidence hashes/counts and replay the existing heterogeneous example."""
from pathlib import Path
import csv,hashlib,json,importlib.util,sys
from inventory import ROOT,OUT

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    checked={};errors=[]
    def check(p,expected):
        p=Path(p)
        if not p.is_absolute():p=ROOT/p
        key=str(p.relative_to(ROOT)).replace('\\','/')
        ok=p.exists() and digest(p)==expected
        checked[key]=ok
        if not ok:errors.append(key)
    snapshots=[]
    for filename in ('current_evidence.json','extended_evidence.json'):
        p=ROOT/'JMS-version/revisions/20261107_completed_experiments'/filename
        d=read(p);snapshots.append({'path':str(p.relative_to(ROOT)), 'sha256':digest(p)})
        for campaign in d['campaigns']:
            check(Path('JMS-version/results')/campaign['name']/'campaign.json',campaign['campaign_sha256'])
            for row in campaign['rows']:
                for r in [row,row.get('before',{})]:
                    if r.get('path') and r.get('sha256'):check(r['path'],r['sha256'])
                    for s,h in r.get('checked_artifact_hashes',{}).items():check(s,h)
    p=ROOT/'JMS-version/results/wafer_multiscale_gantt/gantt/wafer100_mix_50_50_20260825/wafer100_mix_50_50_20260825_validated_solutions.json'
    d=read(p)[0]
    check(d['instance_file'],d['instance_sha256']);check(d['solution_file'],d['solution_sha256'])
    old100={k:v for k,v in d.items() if k!='solution'}
    original=ROOT/'JMS-version/results/heterogeneous100_80_180_90_20261022/initial_schedule.json'
    vp=ROOT/'JMS-version/results/heterogeneous100_80_180_90_20261022/frozen_code/validate.py'
    sys.path.insert(0,str(vp.parent))
    spec=importlib.util.spec_from_file_location('thesis_heterogeneous_validator',vp)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    d=read(original);replay=module.validate(d)
    assert replay['valid'],replay['errors']
    tare=ROOT/'T-ASE-version/results/sensitivity_20260915_133850_532939'
    raw=list(tare.glob('runs/*/*_raw.csv'))
    tase={'files':[str(p.relative_to(ROOT)) for p in raw],'rows':sum(len(list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))) for p in raw),'planned_commands':len(read(tare/'plan.json'))}
    report={'scope':'Hash recheck of saved D/E evidence; M1 100-wafer LP/solution hashes; fresh M3 physical replay; no optimizer', 'snapshots':snapshots,'checked_hashes':checked,'hash_errors':errors,'m1_100':old100,'m3_100':{'source':str(original.relative_to(ROOT)),'source_sha256':digest(original),'validator_sha256':digest(vp),'replay':replay,'original_model_check':d.get('original_model_check'),'global_optimality_claim':d.get('global_optimality_claim')},'tase_sensitivity':tase}
    (OUT/'evidence_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'hashes_checked':len(checked),'hash_errors':errors,'m1_100_status':old100['status'],'m1_100_objective':old100['best_obj'],'m3_100_replay':replay,'tase_sensitivity':tase},ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
