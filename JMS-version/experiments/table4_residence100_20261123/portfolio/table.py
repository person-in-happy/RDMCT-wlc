"""Rebuild native witnesses and write the corrected table as complete case rows arrive."""
from datetime import datetime
from pathlib import Path
from statistics import mean
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inputs import CASES, Config, Integrated, OUT, case_id, cell, product, read, save, sha, validate


def check(path):
    d=read(path)
    src=OUT/d["path"]
    spec=read(OUT/"inputs"/d["case"]/"input.json")
    data=read(src/"schedule.json")
    assert spec["config"]==data["config"] and d["start"]==spec["assignment_sha256"]
    cfg=Config(**spec["config"])
    assert cfg.chamber_residency_basis=="nonprocessing" and cfg.module_residency==cfg.robot_residency==100
    for name,field in (("assignment.json.gz","assignment_sha256"),("schedule.json","schedule_sha256")):
        assert sha(src/name)==d[field]
    x=Integrated(cfg)
    vals=cell.values(src/"assignment.json.gz")
    sol=cell.attach(x,vals)
    decoded=x.result(solution=sol)
    assert all(decoded[k]==data[k] for k in ("events","jobs","cycles","pairs"))
    x.model.freeSol(sol)
    x.model.freeProb()
    assert validate(data)["valid"]
    f=product.product_metrics(data)
    assert f==d["metrics"]
    a,b=f["cmax"],f["secondary"]
    a0,b0=(spec["metrics"][k] for k in ("cmax","secondary"))
    obj={"A":a,"B":b,"J":a/a0+.1*b/b0,"AB":b}[d["arm"]]
    lower,upper=(d["record"][k] for k in ("lower","upper"))
    assert abs(obj-upper)<(2e-4 if d["arm"]!="J" else 2e-4*(1/a0+.1/b0))
    assert lower<=upper+1e-8 and (upper==lower==0 or (lower>0 and upper<=1.1*lower+1e-8))
    if d["arm"]=="AB":
        parent=path.parent.parent/"A/endpoint.json"
        assert d["parent"]==sha(parent) and a<=read(parent)["metrics"]["cmax"]+2e-4
    return dict(case=d["case"],seed=d["seed"],arm=d["arm"],a=a,b=b,hash=sha(path))


def write_table(rows):
    arms=("A","B","J","AB")
    lines=[r"\begin{table}[!htbp]\centering\small",
           r"\caption{100~s非加工驻留上限与10\%相对间隙下四种求解方案的目标值（s）}",
           r"\label{tab:matched-objectives-cn}\setlength{\tabcolsep}{3pt}",
           r"\begin{tabular}{@{}*{7}{c}@{}}\toprule",
           r"片数 & $H$ & 指标 & 仅$f_A$ & 仅$f_B$ & 联合目标 & 两阶段\\\midrule"]
    complete=[]
    for n,h in CASES:
        key=case_id(n,h)
        if not all((key,s,arm) in rows for arm in arms for s in (1,2,3)):
            continue
        if complete:
            lines.append(r"\addlinespace[2pt]")
        complete.append(key)
        for metric,label in (("a","$f_A$"),("b","$f_B$")):
            nums=[mean(rows[key,s,arm][metric] for s in (1,2,3)) for arm in arms]
            lines.append(" & ".join([str(n),str(h),label,*[f"{v:.2f}" for v in nums]])+r"\\")
    lines.append(r"\bottomrule\end{tabular}\end{table}")
    text="\n".join(lines)+"\n"
    if complete:
        tmp=OUT/"table4_current.tex.tmp"
        tmp.write_text(text,encoding="utf8")
        tmp.replace(OUT/"table4_current.tex")
    save(OUT/"table_review.json",dict(verified=len(rows),complete_cases=complete,
         at=datetime.now().astimezone().isoformat(timespec="seconds"),witnesses=list(rows.values())))


if __name__=="__main__":
    rows={}
    while True:
        count=len(rows)
        for p in (OUT/"runs").glob("*/*/endpoint.json"):
            d=read(p)
            key=(d["case"],d["seed"],d["arm"])
            if key not in rows or rows[key]["hash"]!=sha(p):
                rows[key]=check(p)
        if len(rows)!=count:
            write_table(rows)
            print(f"{len(rows)}/60 original model witnesses verified",flush=True)
        if len(rows)==60 or "--once" in sys.argv:
            break
        time.sleep(30)
