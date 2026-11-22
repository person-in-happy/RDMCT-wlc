"""Relate flat event exports to their full schedules and index secondary-score summaries."""
from collections import Counter
import csv
import json
import re
import subprocess
from pathlib import Path
from objective import ROOT, JMS

OUT=JMS/"results/product_wait_20261122/audit"


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    files=subprocess.check_output(["rg","--files","--hidden","--no-ignore","-g","!.git",
        "-g","!JMS-version/results/product_wait_20261122/**","-g","*.csv","-g","*.jsonl","-g","*.tsv",
        "-g","*.parquet","-g","*.xlsx"],cwd=ROOT).decode("utf8").splitlines()
    files=[name for name in files if not (ROOT/name).is_relative_to(OUT.parent)]
    indexed={r["source"]:r for r in csv_rows(OUT/"schedule_scores.csv") if r["location"]==""}
    exports=[];metrics=[];other=Counter();issues=[]
    for name in files:
        path=ROOT/name
        if path.name=="events.csv":
            src=path.with_name("result.json")
            if not src.exists():
                issues.append([name,"missing corresponding JSON"])
                continue
            doc=json.loads(src.read_bytes())
            for field in ("jobs","events","cycles"):
                rows=csv_rows(path.with_name(field+".csv"))
                raw=doc[field]
                if len(rows)!=len(raw):
                    raise ValueError(f"{path} {field}: different record count")
                for a,b in zip(rows,raw):
                    for k in ("name","identity","product","kind","start","end","unload_end","load_start"):
                        if k in a and a[k] and k in b:
                            if k in ("start","end","unload_end","load_start"):
                                assert abs(float(a[k])-b[k])<1e-5,(path,k)
                            else: assert a[k]==str(b[k]),(path,k)
            source=src.relative_to(ROOT).as_posix()
            exports.append(dict(events=path.relative_to(ROOT).as_posix(),source=source,
                                status=indexed.get(source,{}).get("status","no_scored_schedule")))
        elif path.suffix==".jsonl":
            with path.open(encoding="utf-8-sig") as f:
                for line in f:
                    if re.search(r'"(?:events|jobs)"\s*:',line):
                        issues.append([name,"event keys in line-delimited JSON"])
                        break
            other["jsonl_files"]+=1
        elif path.suffix in (".csv",".tsv"):
            with path.open(encoding="utf-8-sig",errors="replace") as f: header=f.readline().strip()
            if re.search(r'secondary|wait_sum|wait_max|route.wait|f_b|工艺目标|总等待',header,re.I):
                metrics.append(dict(source=path.relative_to(ROOT).as_posix(),columns=header))
            other["flat_tables"]+=1
        else: other[path.suffix]+=1
    report=dict(scanned=len(files),verified_event_exports=exports,aggregate_metric_files=metrics,
                other=other,unresolved=issues)
    (OUT/"flat_exports.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(len(exports),len(metrics),len(issues),other,flush=True)


if __name__=="__main__":
    main()
