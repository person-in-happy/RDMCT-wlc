"""Index archived event schedules without altering published raw histories or solver bounds."""
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

from objective import ROOT, JMS, physical_metrics, product_metrics

OUT=JMS/"results/product_wait_20261122/audit"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths=subprocess.check_output(["rg","--files","--hidden","--no-ignore","-g","*.json","-g","*.json.gz",
                                  "-g","!.git","-g","!JMS-version/results/product_wait_20261122/**"],cwd=ROOT).decode("utf8").splitlines()
    groups=defaultdict(Counter)
    rows=[]
    transitions=Counter()
    cached={}
    issues=[]
    for filename in paths:
        path=ROOT/filename
        parts=Path(filename).parts
        if path.is_relative_to(OUT.parent):
            continue
        group="/".join(parts[:3]) if parts[:2]==("JMS-version","results") else parts[0]
        groups[group]["json_files"]+=1
        try:
            with (gzip.open(path,"rb") if path.suffix==".gz" else path.open("rb")) as f:
                head=f.read(768)
                if re.match(br'^\s*\{\s*"(values|nonzero|jp_active_0|pj_active_0)"\s*:',head):
                    groups[group]["assignment_only"]+=1
                    continue
                raw=head+f.read()
            if b'"events"' not in raw or b'"jobs"' not in raw:
                if re.search(br'"(?:route_wait_sum|wait_sum|max_wait|secondary)"\s*:',raw):
                    groups[group]["metrics_or_schema_without_events"]+=1
                continue
            sha=hashlib.sha256(raw).hexdigest()
            if sha not in cached:
                obj=json.loads(raw)
                stack=[("",obj)]
                found=[]
                while stack:
                    key,obj=stack.pop()
                    if isinstance(obj,dict):
                        if all(k in obj for k in ("events","jobs","config","cycles")) and isinstance(obj["jobs"],list):
                            if not obj["jobs"] or not obj["events"]:
                                found.append(dict(location=key,status="empty_event_schedule"))
                                continue
                            try:
                                orig=physical_metrics(obj)
                                prod=product_metrics(obj)
                                recorded=obj.get("validation",{}) or {}
                                valid=recorded.get("valid")
                                status="invalid_archived" if valid is False else "event_rescore"
                                found.append(dict(location=key,status=status,recorded_replay=valid,
                                    cmax=prod["cmax"],all_wait_sum=orig["wait_sum"],all_wait_max=orig["wait_max"],
                                    all_secondary=orig["secondary"],product_wait_sum=prod["wait_sum"],
                                    product_wait_max=prod["wait_max"],rhythm=prod["rhythm"],
                                    rhythm_centers=prod["rhythm_centers"],product_secondary=prod["secondary"]))
                            except (TypeError,ValueError,KeyError,IndexError,AttributeError) as exc:
                                found.append(dict(location=key,status="incompatible_or_incomplete_events",reason=str(exc)))
                            continue
                        stack.extend((key+"/"+k,v) for k,v in obj.items() if isinstance(v,(list,dict)))
                    elif isinstance(obj,list):
                        stack.extend((key+"/"+str(i),v) for i,v in enumerate(obj) if isinstance(v,(dict,list)))
                cached[sha]=found
            for row in cached[sha]:
                groups[group][row["status"]]+=1
                transitions[row["status"]]+=1
                rows.append(dict(source=path.relative_to(ROOT).as_posix(),sha256=sha,**row))
        except (OSError,ValueError) as exc:
            issues.append(dict(source=filename,reason=str(exc)))
    fields=["source","sha256","location","status","recorded_replay","cmax","all_wait_sum","all_wait_max",
            "all_secondary","product_wait_sum","product_wait_max","rhythm","rhythm_centers","product_secondary","reason"]
    with (OUT/"schedule_scores.csv").open("w",encoding="utf-8-sig",newline="") as out:
        writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    scanned=sum(counts["json_files"] for counts in groups.values())
    (OUT/"inventory.json").write_text(json.dumps(dict(scanned=scanned,groups=groups,records=transitions,read_issues=issues),
                                           ensure_ascii=False,indent=2),encoding="utf8")
    print(scanned,len(rows),dict(transitions),len(issues),flush=True)


if __name__=="__main__":
    main()
