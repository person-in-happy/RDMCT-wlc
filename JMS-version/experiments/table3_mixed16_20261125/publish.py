"""Publish complete 16-wafer mixed results in the eight-wafer grid CSV schema."""
import csv
import os
from campaign import OUT,JMS,GAPS,sha,read
from verify import verify


def publish():
    history=read(OUT/"stream.json")
    assert set(history["gates"])==set(GAPS)
    rows=[]
    for a,event in history["gates"].items():
        parent=OUT/event["path"]
        for b in GAPS:
            location=OUT/"grid"/a/b
            cert=location/"result.json";r=read(cert)
            assert r["parents"][0]["schedule_sha256"]==sha(parent/"schedule.json")
            assert r["parents"][0]["assignment_sha256"]==sha(parent/"assignment.json.gz")
            physical=r["measured"];dual=r["record"]
            rows.append(dict(case="D_n16_H10_mixed_dual",recipe="mixed",gA=a,gB=b,
                f_A=physical["cmax"],f_B=physical["secondary"],mean=physical["mean_residence"],
                spread=physical["residence_range"],E=physical["clean_deficit"],A_lower=event["lower"],
                A_upper=event["upper"],A_gap=event["gap"],B_lower=dual["lower"],B_upper=dual["upper"],B_gap=dual["gap"],
                reused=False,A_source=parent.relative_to(JMS).as_posix(),A_sha256=event["record_sha256"],
                source=location.relative_to(JMS).as_posix(),schedule_sha256=r["files"]["schedule.json"],
                assignment_sha256=r["files"]["assignment.json.gz"],B_sha256=sha(cert),A_bound=event["lower_source"],
                A_bound_sha256=event["lower_sha256"]))
    dest=OUT/"threshold_cells.csv"
    tmp=dest.with_suffix(".tmp")
    with tmp.open("w",encoding="utf8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    os.replace(tmp,dest)
    verify()

if __name__=="__main__":publish()
