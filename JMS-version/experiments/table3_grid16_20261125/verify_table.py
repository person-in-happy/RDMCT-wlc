"""Join and audit all threshold experiments, along with the printed tables and original figures."""
import argparse
import importlib.util
from itertools import product
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("grid8",HERE.parent/"table3_grid8_20261125/verify.py")
g=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
JMS=g.JMS
OUT=g.RESULTS/"table3_grid16_20261125"
SIXTEEN=("D_n16_pure_4x1","D_n16_pure_2x2","D_n16_H10_mixed_dual")
CASES=g.OLD_CASES+g.NEW_CASES+SIXTEEN


def new_cells():
    rows={}
    sources=(g.RESULTS/"table3_pure16_20261125/threshold_cells.csv",
             g.RESULTS/"table3_mixed16_20261125/threshold_cells.csv")
    for path in sources:
        if not path.exists():
            continue
        for r in g.audit.csv_rows(path):
            key=(r["case"],r["gA"],r["gB"])
            assert key not in rows and key[0] in SIXTEEN
            source=JMS/r["A_proof"] if r.get("A_proof") else JMS/r["A_source"]/"primary.json"
            a=g.audit.read(source)
            folder=JMS/r["source"] if r.get("source") else (JMS/r["B_proof"]).parent
            b=g.audit.read(folder/"result.json")
            assert b["eligible"] and b["replay"]["valid"] and b["seed"]==1
            assert a["rows"]>0 and a["replay"]["valid"]
            a_file=source.parent/"schedule.json"
            assert g.digest(a_file)==a["schedule_sha256"]==b["parents"][0]["schedule_sha256"]
            assert g.digest(source.parent/"assignment.json.gz")==a["assignment_sha256"]==b["parents"][0]["assignment_sha256"]
            if "lower_source" in a:
                assert g.digest(JMS/a["lower_source"])==a["lower_sha256"]
                ab=a
            else:
                stream=g.audit.read(g.RESULTS/"table3_mixed16_20261125/stream.json")
                ab=stream["gates"][key[1]]
                assert g.digest(source)==ab["record_sha256"] and g.digest(JMS/ab["lower_source"])==ab["lower_sha256"]
            for filename,sha in b["files"].items():
                assert g.digest(folder/filename)==sha
            p=folder/"schedule.json"
            schedule=g.audit.read(p)
            assert g.digest(p)==r["schedule_sha256"]
            cfg=schedule["config"]
            assert (cfg["horizon"],cfg["cleaning_interval"],cfg["dummy_count"],cfg["module_residency"],cfg["robot_residency"])==(100000,10,8,100,100)
            want={"4x1":(4,0),"2x2":(0,4),"mixed":(2,2)}[r["recipe"]]
            assert list(cfg["load_ports"])==["LP1","LP2","LP3","LP4"]
            assert all(tuple(s[k] for k in ("4x1","2x2"))==want for s in cfg["load_ports"].values())
            physical=g.independent(schedule)
            g.audit.check_fields(physical,r,dict(cmax="f_A",secondary="f_B",mean_residence="mean",residence_range="spread",clean_deficit="E"))
            assert b["original_rows"]==b["replayed_rows"]>0
            bounds={}
            for k,raw,level in (("A",ab,key[1]),("B",b["record"],key[2])):
                for col in ("upper","lower","gap"):
                    val=raw[col];bounds[k+"_"+col]=val
                    assert abs(float(r[k+"_"+col])-val)<2e-5
                assert raw["upper"]-raw["lower"]<=g.LEVELS[level]*abs(raw["lower"])+2e-5
                assert raw["lower"]<=raw["upper"]+2e-5 and raw["gap"]<=g.LEVELS[level]+1e-7
            assert abs(physical["cmax"]-bounds["A_upper"])<2e-4
            assert abs(physical["secondary"]-bounds["B_upper"])<2e-4
            rows[key]=dict(case=key[0],gA=key[1],gB=key[2],seed=1,f_A=physical["cmax"],
                           f_B=physical["secondary"],mean=physical["mean_residence"],spread=physical["residence_range"],
                           clean_deficit=physical["clean_deficit"],huber=physical["huber_penalty"],**bounds,
                           schedule_path=p.relative_to(JMS).as_posix(),schedule_sha256=r["schedule_sha256"],
                           primary_schedule_sha256=a["schedule_sha256"],source_csv=path.relative_to(JMS).as_posix())
    return rows


def main(check_only):
    grid=g.get_grid()|new_cells()
    print(f"{len(grid)}/108 threshold cells verified from native schedules.")
    if check_only:return
    order=list(product(CASES,g.LEVELS,g.LEVELS))
    assert set(grid)==set(order)
    for case,a in product(CASES,g.LEVELS):
        assert len({grid[case,a,b]["primary_schedule_sha256"] for b in g.LEVELS})==1
    ranking,choice,tradeoffs=g.summarize(grid,CASES)
    g.write_csv(OUT/"threshold_cells.csv",[grid[k] for k in order])
    g.write_csv(OUT/"normalized_means.csv",ranking)
    g.audit.independent=g.independent
    dest=OUT/"manuscript_validation.json"
    extra=g.NEW_CASES+SIXTEEN
    g.audit.main(False,True,extra_grid=[grid[k] for k in order if k[0] in extra],
                 extra_cases=extra,display_cases=CASES,with_hit_column=False,validation_path=dest)
    import json
    report=g.audit.read(dest)|g.verify_front_and_figures()
    report.update(selected_thresholds=choice,observed_tradeoff_cases=tradeoffs,displayed_cases=CASES,
                  full_grid_sha256=g.digest(OUT/"threshold_cells.csv"),pdf_sha256=g.digest(JMS/"JMS_Review_CN.pdf"))
    dest.write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--check-only",action="store_true")
    main(parser.parse_args().check_only)
