"""Reconstruct every schedule under its original backend before pooling any seeds."""
import csv
from pathlib import Path
from statistics import mean
import subprocess
import sys

from solve import (ARMS, CASES, HERE, JMS, LEVELS, OUT, ROOT, SEEDS, cell, directory,
                   objective, product, read, require_threshold, save, sha)


def verify_case(case):
    spec = read(OUT / "protocol.json")["inputs"][case]
    schedule, assignment = (ROOT / spec[k] for k in ("source", "assignment"))
    assert (sha(schedule), sha(assignment)) == (spec["source_sha256"], spec["assignment_sha256"])
    start = product.product_metrics(read(schedule))
    sys.path.insert(0, str(cell.BACKENDS[spec["backend"]]))
    import model
    from validate import validate
    x = model.Integrated(model.Config(**spec["config"]))
    discrete = [v.name for v in x.model.getVars(transformed=False)
                if v.vtype() != "CONTINUOUS" and not v.name.startswith("sync_")]
    rows = []
    for seed in SEEDS:
        for level in LEVELS:
            for arm in ARMS:
                folder = directory(case, seed, arm) / level
                rec = read(folder / "result.json")
                assert (rec["case"], rec["seed"], rec["arm"], rec["level"]) == (case, seed, arm, level)
                assert rec["start"] == spec["assignment_sha256"] and rec["replay"]
                dest = folder / "runs/endpoint" if arm == "AB" else folder
                for name, key in (("schedule.json", "schedule"), ("assignment.json.gz", "assignment")):
                    assert ROOT / rec[key] == dest / name and sha(dest / name) == rec["hashes"][name]
                events = read(dest / "schedule.json")
                assert events["config"] == spec["config"] and validate(events)["valid"]
                values = cell.values(dest / "assignment.json.gz")
                sol = cell.attach(x, values)
                native = x.result(solution=sol)
                x.model.freeSol(sol)
                # Stage A may tighten the unused Cmax epigraph. No physical timestamp changes.
                for field in ("jobs", "cycles", "events", "pairs"):
                    assert native[field] == events[field], (case, seed, level, arm, field)
                scores = product.product_metrics(events)
                for field in scores:
                    assert abs(scores[field] - rec["metrics"][field]) <= cell.EPS
                actual_gap = require_threshold(rec["record"], level)
                allowed = objective(arm, dict(cmax=cell.EPS, secondary=cell.EPS), start)
                assert abs(objective(arm, scores, start) - rec["record"]["upper"]) <= allowed
                if arm == "AB":
                    parent = directory(case, seed, "A") / level
                    a = read(parent / "result.json")
                    b = read(dest / "result.json")
                    assert rec["handoff_hash"] == sha(parent / "result.json")
                    assert b["job"]["assignment_sha256"] == sha(parent / "assignment.json.gz")
                    assert b["job"]["schedule_sha256"] == sha(parent / "schedule.json")
                    assert b["job"]["seconds"] is None and b["job"]["gap"] == LEVELS[level]
                    assert b["job"]["kind"] == "fixed" and b["eligible"] and b["replay"]["valid"]
                    handoff = cell.values(parent / "assignment.json.gz")
                    assert all(round(values.get(k, 0.)) == round(handoff.get(k, 0.)) for k in discrete)
                    assert scores["cmax"] <= a["metrics"]["cmax"] + 1e-6 + cell.EPS
                    assert scores["secondary"] <= a["metrics"]["secondary"] + cell.EPS
                rows.append(dict(case=case, seed=seed, level=level, arm=arm, f_A=scores["cmax"],
                                 f_B=scores["secondary"], product_wait_sum=scores["wait_sum"],
                                 product_wait_max=scores["wait_max"], rhythm=scores["rhythm"],
                                 record=rec["record"], actual_gap=actual_gap, schedule=rec["schedule"],
                                 schedule_sha256=rec["hashes"]["schedule.json"], start=rec["start"]))
    x.model.freeProb()
    save(OUT / "audit" / (case + ".json"), rows)


def tabulate(rows):
    groups = {(r["case"], r["level"], r["arm"], r["seed"]): r for r in rows}
    assert len(rows) == len(groups) == len(CASES)*len(LEVELS)*len(ARMS)*len(SEEDS)
    table = []
    order = sorted(CASES, key=lambda c: tuple(int(k[1:]) for k in c.split("_")[1:3]))
    for level in LEVELS:
        for case in order:
            n, h = (int(k[1:]) for k in case.split("_")[1:3])
            row = dict(level=level, wafers=n, H=h)
            for arm in ARMS:
                for metric in ("f_A", "f_B"):
                    row[f"{arm}_{metric}"] = mean(groups[case, level, arm, s][metric] for s in SEEDS)
            table.append(row)
    return table


def table_tex(table):
    lines = [r"\begin{table*}[!htbp]\ContinuedFloat\centering\small",
             r"\caption[]{（续）四种求解方案在固定相对间隙下的工期与工艺目标值（s）}",
             r"\label{tab:matched-objectives-gaps-cn}",
             r"\begin{tabular}{@{}ccc*{8}{r}@{}}\toprule",
             r" & & & \multicolumn{2}{c}{仅$f_A$} & \multicolumn{2}{c}{仅$f_B$} & \multicolumn{2}{c}{联合目标} & \multicolumn{2}{c}{两阶段}\\",
             r"\cmidrule(lr){4-5}\cmidrule(lr){6-7}\cmidrule(lr){8-9}\cmidrule(l){10-11}",
             r"相对间隙 & 片数 & $H$ & $f_A$ & $f_B$ & $f_A$ & $f_B$ & $f_A$ & $f_B$ & $f_A$ & $f_B$\\\midrule"]
    previous = None
    for row in table:
        level = row["level"]
        label = ""
        if level != previous:
            if previous:
                lines.append(r"\addlinespace[3pt]")
            label = f"{100*LEVELS[level]:g}" + r"\%"
        values = [f"{row[arm+'_'+metric]:.2f}" for arm in ARMS for metric in ("f_A", "f_B")]
        lines.append(" & ".join([label, str(row["wafers"]), str(row["H"]), *values]) + r"\\")
        previous = level
    lines += [r"\bottomrule\end{tabular}\par\smallskip",
              r"{\footnotesize 单目标与联合目标按各自目标的相对间隙停机。两阶段采用相同的工期切换阈值和工艺停机阈值。}",
              r"\end{table*}"]
    return "\n".join(lines)


def finish():
    for case in CASES:
        subprocess.run([sys.executable, "-B", "-X", "utf8", str(Path(__file__)), case], cwd=ROOT, check=True)
    rows = [r for case in CASES for r in read(OUT / "audit" / (case + ".json"))]
    table = tabulate(rows)
    for name, records in (("endpoints", rows), ("table4_means", table)):
        with (OUT / (name + ".csv")).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    (OUT / "table4_gap.tex").write_text(table_tex(table), encoding="utf8")
    subprocess.run(["G:/conda/python.exe", "-B", "-X", "utf8", str(HERE / "publish.py")], cwd=ROOT, check=True)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        verify_case(sys.argv[1])
    else:
        finish()
