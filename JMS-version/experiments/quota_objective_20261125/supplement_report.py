"""Summarize only hash-verified logical cells and reproduce the threshold choice."""
import csv
import statistics
from supplement import OUT, checked, load, save


def report():
    jobs = load(OUT / "manifest.json")
    grid, structure = [], []
    for name, job in jobs.items():
        dest = OUT / job["key"]
        if not checked(dest, job):
            raise ValueError(f"Unverified cell {name}")
        result = load(dest / "result.json")
        row = dict(name=name, seed=result["seed"], status=result["record"]["status"],
                   f_A=result["measured"]["cmax"], f_B=result["measured"]["secondary"],
                   mean=result["measured"]["mean_residence"], spread=result["measured"]["residence_range"],
                   quota=result["measured"]["quota_unused"], production=result["measured"]["production_count"],
                   cleans=result["measured"]["clean_count"], handoff_B=result["initial"]["secondary"],
                   lower=result["record"]["lower"], gap=result["record"]["gap"], source=job["key"])
        if name.startswith("grid_"):
            case, gA, gB = name[5:].split("__")
            grid.append(dict(case=case, gA=gA, gB=gB, **row))
        else:
            structure.append(row)
    for filename, rows in (("threshold_cells.csv",grid),("structure_cells.csv",structure)):
        with (OUT / filename).open("w",newline="",encoding="utf8") as output:
            table = csv.DictWriter(output,fieldnames=list(rows[0]))
            table.writeheader()
            table.writerows(rows)
    levels = {"10pct":.1, "1pct":.01, "0p01pct":.0001}
    scores = []
    for a in levels:
        for b in levels:
            first, second = [], []
            for row in grid:
                if (row["gA"],row["gB"]) != (a,b):
                    continue
                rows = [entry for entry in grid if entry["case"]==row["case"]]
                for target, field in ((first,"f_A"),(second,"f_B")):
                    best = min(other[field] for other in rows)
                    target.append(row[field]/(best if best>1e-6 else 1.))
            scores.append(dict(gA=a,gB=b,mean_norm_A=statistics.mean(first),mean_norm_B=statistics.mean(second)))
    chosen = min(scores,key=lambda s:(round(s["mean_norm_A"],8),round(s["mean_norm_B"],8),
                                      -levels[s["gA"]],-levels[s["gB"]]))
    save(OUT / "threshold_selection.json",dict(scores=scores,chosen=chosen,logical_cells=len(grid)))
    print(chosen)


if __name__=="__main__":
    report()
