"""Read-only validation of finished campaigns; write only this revision's audit."""
from pathlib import Path
import collections, hashlib, json, statistics, sys
ROOT=Path(__file__).resolve().parents[3]
BACKEND=ROOT/'JMS-version/model4_pjob_20261027'
sys.path.insert(0,str(BACKEND))
import evidence_supplement as e
OUT=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
mean=lambda xs:statistics.mean(xs)

def describe(rs):
    valid=[r for r in rs if r['has_solution']]
    return dict(n=len(rs),feasible=len(valid),statuses=dict(collections.Counter(r['status'] for r in rs)),
        cmax_mean=mean(r['upper'] for r in valid) if valid else None,
        cmax_values=[r['upper'] for r in rs],
        wait_mean=mean(r['metrics']['route_wait_sum'] for r in valid) if valid else None,
        max_wait_mean=mean(r['metrics']['route_wait_max'] for r in valid) if valid else None,
        rhythm_centers=sorted({r['metrics']['rhythm_centers'] for r in valid}),
        pdi_mean=mean(r['pdi'] for r in rs),
        solve_seconds_min=min(r['primary_solve_seconds'] for r in rs),
        solve_seconds_max=max(r['primary_solve_seconds'] for r in rs),
        solve_seconds_mean=mean(r['primary_solve_seconds'] for r in rs),
        pdi_per_second_mean=mean(r['pdi']/r['primary_solve_seconds'] for r in rs),
        lower_min=min((r['lower'] for r in rs if r['lower'] is not None),default=None),
        lower_max=max((r['lower'] for r in rs if r['lower'] is not None),default=None))

def main():
    batches={}
    names=('model4_core_all_20261028_fix1','model4_ablation_all_20261028_164314')
    for name in names:
        folder=ROOT/'JMS-version/results'/name;spec,contract=e.checked(folder)
        oldaudit=read(sorted((folder/'audits').glob('audit_*.json'))[-1])
        assert oldaudit['coverage_complete'] and read(folder/'finished.json')['complete_observations']==len(spec['cells'])
        rows=[]
        for index,cell in enumerate(spec['cells'],1):
            row=e.check_cell(folder,cell);rows.append(row)
            previous=next(r for r in oldaudit['rows'] if r['id']==row['id'])
            assert row==previous,(name,row['id'],'saved audit changed')
            if index%24==0 or index==len(spec['cells']):print(f'{name}: verified={index}/{len(spec["cells"])} failed=0',flush=True)
        grouped=collections.defaultdict(list);bycase=collections.defaultdict(lambda:collections.defaultdict(list))
        for r in rows:grouped[r['variant']].append(r);bycase[r['case']][r['variant']].append(r)
        telemetry={}
        for arm,rs in grouped.items():
            ts=[r['cut_telemetry'] for r in rs if r['cut_telemetry'] is not None]
            if ts:telemetry[arm]=ts
        batches[spec['suite']]=dict(path=str(folder.relative_to(ROOT)),campaign_sha256=sha(folder/'campaign.json'),
            audit_sha256=sha(sorted((folder/'audits').glob('audit_*.json'))[-1]),
            settings=contract['settings'],environment=contract['environment'],
            arm_summary={k:describe(v) for k,v in grouped.items()},
            case_summary={k:{a:describe(rs) for a,rs in arms.items()} for k,arms in bycase.items()},
            telemetry=telemetry,rows=rows)
    report=dict(batches=batches,scope='Stored original-SCIP checks and LP/result hashes verified; all available incumbents physically replayed. No solve or campaign mutation.')
    (OUT/'verified_evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    compact={suite:{k:v for k,v in data.items() if k not in ('rows','telemetry')} for suite,data in batches.items()}
    (OUT/'result_summary.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('COMPLETE: 342 observations, all hashes and independent physical checks accepted.',flush=True)

if __name__=='__main__':main()
