"""Verify every available 16-wafer grid cell and its earliest physical handoff."""
import csv
import json
import math
import sys
from pathlib import Path
from campaign import OUT,HERE,JMS,GAPS,read,sha,save
sys.path.insert(0,str(HERE.parent/"huber_residence_20261125"))
from verify_manuscript import independent


def verify():
    history=read(OUT/"stream.json")
    config=read(OUT/"input.json")["config"]
    assert config["load_ports"]=={f"LP{k}":{"4x1":2,"2x2":2} for k in range(1,5)}
    assert (config["source"],config["dummy_count"],config["cleaning_interval"],config["full_time"],config["mix_time"],
            config["module_residency"],config["robot_residency"],config["horizon"])==("dual",8,10,180,90,100,100,100000)
    for prev,event in zip(history["events"],history["events"][1:]):
        assert prev["upper"]>=event["upper"] and prev["lower"]<=event["lower"]
    audited=set()
    for event in history["events"]:
        native=OUT/event["path"]
        record=native/"primary.json"
        assert sha(record)==event["record_sha256"]
        assert sha(JMS/event["lower_source"])==event["lower_sha256"]
        assert read(JMS/event["lower_source"])["lower"]==event["lower"]
        assert math.isclose((event["upper"]-event["lower"])/event["lower"],event["gap"],abs_tol=1e-10)
        if record in audited:continue
        audited.add(record)
        data=read(record)
        assert data["rows"]==1109436 and data["replay"]["valid"] and data["replay"]["pjob_release_order_check"]
        assert data["schedule_sha256"]==sha(native/"schedule.json") and data["assignment_sha256"]==sha(native/"assignment.json.gz")
        doc=read(native/"schedule.json")
        assert doc["config"]==config
        assert math.isclose(independent(doc)["cmax"],event["upper"],abs_tol=2e-6)
    for a,tau in GAPS.items():
        first=next((e for e in history["events"] if e["gap"]<=tau+1e-10),None)
        assert first==history["gates"].get(a)
    published=OUT/"threshold_cells.csv"
    cells=list(csv.DictReader(published.open(encoding="utf8",newline=""))) if published.exists() else []
    assert len({(r["gA"],r["gB"]) for r in cells})==len(cells)
    evidence=[]
    for row in cells:
        a,b=row["gA"],row["gB"]
        parent=history["gates"][a]
        home=JMS/row["source"]
        file=home/"result.json"
        r=read(file)
        assert r["seed"]==1 and r["mode"]=="fixed" and r["target_gap"]==GAPS[b]
        assert r["eligible"] and r["replay"]["valid"] and r["original_rows"]==r["replayed_rows"]==1109436
        assert sha(home/"schedule.json")==row["schedule_sha256"] and all(sha(home/k)==v for k,v in r["files"].items())
        assert r["parents"][0]["assignment_sha256"]==sha(OUT/parent["path"]/"assignment.json.gz")
        assert math.isclose(float(row["A_lower"]),parent["lower"],abs_tol=1e-8)
        assert math.isclose(float(row["A_upper"]),parent["upper"],abs_tol=1e-8)
        physical=independent(read(home/"schedule.json"))
        for k,n in (("f_A","cmax"),("f_B","secondary"),("mean","mean_residence"),("spread","residence_range"),("E","clean_deficit")):
            assert math.isclose(float(row[k]),physical[n],abs_tol=2e-6)
        assert physical["cmax"]<=parent["upper"]+2e-6
        upper,lower=r["record"]["upper"],r["record"]["lower"]
        assert upper>=lower-2e-6 and (upper-lower)/max(lower,1e-9)<=GAPS[b]+1e-7
        evidence.append(dict(gA=a,gB=b,A_record_sha256=parent["record_sha256"],A_global_lower_sha256=parent["lower_sha256"],
                             B_result_sha256=sha(file),schedule_sha256=r["files"]["schedule.json"],assignment_sha256=r["files"]["assignment.json.gz"]))
    report=dict(status="passed" if len(cells)==9 else "validated_partial",rows=len(cells),expected=9,
                native_rows_per_endpoint=1109436,recorded_events=len(history["events"]),distinct_primary_records=len(audited),
                upper=history["events"][-1]["upper"],lower=history["events"][-1]["lower"],gates=list(history["gates"]),
                cells=evidence,csv_sha256=sha(published) if published.exists() else None)
    save(OUT/"validation.json",report)
    print(report["status"],report["rows"],report["upper"],report["lower"])

if __name__=="__main__":verify()
