"""Re-solve the frozen N16/H5/pure22 product model with its validated 907 s start."""
from pathlib import Path
import argparse,csv,datetime,hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--time-limit',type=float,default=28800)
    p.add_argument('--seed',type=int,default=1)
    p.add_argument('--output-dir',default='')
    p.add_argument('--prepare-only',action='store_true')
    a=p.parse_args()
    if a.time_limit<=0 or a.seed<0:p.error('time limit must be positive; seed must be nonnegative')
    from cie.code.analyze_cie_solutions import _validate,_parse_solution,_metrics
    from scip_imports import scip
    source=ROOT/'JMS/results/mode_cleaning_crossover/jms_product_cmax_n8_n16_H4_H9_20260904/validation/cie_manufacturing_metrics.csv'
    rows=list(csv.DictReader(source.open(encoding='utf-8-sig')))
    row=next(x for x in rows if x['suite']=='mode_n016_clean05_pure22')
    inst=ROOT/'JMS-version/results/frozen_models_20260906'/Path(row['path']).name
    warm=Path(row['solution_file'])
    ok,note=_validate(inst,warm)
    if not ok:raise RuntimeError(note)
    out=Path(a.output_dir).resolve() if a.output_dir else ROOT/'JMS/results/submission_evidence'/('h5_certificate_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True,exist_ok=False)
    frozen=out/inst.name;start=out/'initial_907.sol';shutil.copy2(inst,frozen);shutil.copy2(warm,start)
    report={'source_table':str(source),'instance_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),'warm_start_sha256':hashlib.sha256(start.read_bytes()).hexdigest(),'warm_start_validated':ok,'warm_start_cmax':_parse_solution(start)['c_max'],'time_limit':a.time_limit,'seed':a.seed,'objective':'product return Cmax','purpose':'optimality certificate, not a fixed-budget algorithm comparison','prepared_only':a.prepare_only}
    if not a.prepare_only:
        m=scip.Model();m.readProblem(str(frozen));removed=[]
        for c in list(m.getConss()):
            if c.name=='schedule_stability_def' or c.name.startswith(('schedule_wait_def_','resource_idle_')):
                removed.append(c.name);m.delCons(c)
        m.setRealParam('limits/time',a.time_limit);m.setRealParam('limits/memory',4096)
        m.setIntParam('randomization/randomseedshift',a.seed);m.setLogfile(str(out/'solve.log'))
        sol=m.readSolFile(str(start))
        if not m.checkSol(sol):raise RuntimeError('frozen warm start rejected')
        m.addSol(sol);m.optimize()
        report.update(status=str(m.getStatus()),solving_time=m.getSolvingTime(),gap=m.getGap(),dual_bound=m.getDualbound(),primal_bound=m.getObjVal() if m.getNSols() else None,removed_auxiliary_constraints=removed)
        if m.getNSols():
            dest=out/'best.sol';m.writeSol(m.getBestSol(),str(dest));m.freeProb()
            ok,note=_validate(frozen,dest)
            if not ok:raise RuntimeError(note)
            report.update(validated=ok,validation_note=note,metrics=_metrics({},_parse_solution(dest)),solution_sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
        else:m.freeProb()
    (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
