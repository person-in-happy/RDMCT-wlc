"""Render the two standalone tables whenever a new verified endpoint becomes available."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import sys
from statistics import mean

from queue_runs import HERE,JMS,LEGACY,METHODS,RUNROOT,TABLE4_CASES,TABLE4_TOTAL,endpoint,read,write

PAPER=JMS/"revisions/20261124_table45_gap_update"
T4=RUNROOT/"table4_three_arms_20261124"
T5=RUNROOT/"table5_one_percent_20261124"
LABELS=("完整策略（RL-DMCT）","HEM选割","SCIP默认选割","关闭选割重排","省略分层初始化")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify4(path):
    sys.path.insert(0,str(HERE.parent/"table4_residence100_20261123/portfolio"))
    import table
    d=read(path)
    base=LEGACY if path.is_relative_to(LEGACY) else T4
    src=base/d["path"]
    spec=read(LEGACY/"inputs"/d["case"]/"input.json")
    sched=read(src/"schedule.json")
    assert digest(src/"schedule.json")==d["schedule_sha256"] and digest(src/"assignment.json.gz")==d["assignment_sha256"]
    assert spec["config"]==sched["config"] and spec["assignment_sha256"]==d["start"]
    assert sched["config"]["chamber_residency_basis"]=="nonprocessing" and sched["config"]["module_residency"]==100
    assert table.validate(sched)["valid"] and table.product.product_metrics(sched)==d["metrics"]
    x=table.Integrated(table.Config(**spec["config"]))
    s=table.cell.attach(x,table.cell.values(src/"assignment.json.gz"))
    replay=x.result(solution=s)
    assert all(replay[k]==sched[k] for k in ("events","jobs","cycles","pairs"))
    x.model.freeSol(s)
    x.model.freeProb()
    ub,lb=d["record"]["upper"],d["record"]["lower"]
    assert lb<=ub+1e-8 and ub<=1.1*lb+1e-8
    a,b=(d["metrics"][k] for k in ("cmax","secondary"))
    assert abs(ub-(a if d["arm"]=="A" else b))<2e-4
    if d["arm"]=="AB":
        parent=path.parent.parent/"A/endpoint.json"
        assert digest(parent)==d["parent"] and a<=read(parent)["metrics"]["cmax"]+2e-4
    return [a,b]

def verify5(path):
    d=read(path)
    r=read(path.with_name("result.json"))
    assert digest(path.with_name("result.json"))==d["result_sha256"] and r["verified"]
    assert digest(path.with_name("handoff.json"))==r["handoff_sha256"]
    bdir=path.parent/"B/runs/endpoint"
    b=read(bdir/"result.json")
    assert b["job"]["gap"]==.01 and b["eligible"] and b["replay"]["valid"] and b["record"]["gap"]<=.01+1e-9
    assert b["job"]["assignment_sha256"]==digest(path.parent/"A/assignment.json.gz")
    assert all(digest(bdir/k)==v for k,v in b["files"].items())
    a=r["gate"]
    assert a["lower"]<=a["upper"]+1e-8 and a["upper"]<=1.01*a["lower"]+1e-8
    assert d["calls"]==a["calls"] and isinstance(d["calls"],int)
    return [d[k] for k in ("f_A","f_B_handoff","f_B","total_s","calls")]

def gather(cache):
    four,five={},{}
    def checked(path,fn):
        key=str(path.relative_to(JMS))
        h=digest(path)
        if key not in cache or cache[key][0]!=h:
            cache[key]=[h,fn(path)]
        return cache[key][1]
    for n,h in TABLE4_CASES:
        for s in (1,2,3):
            for arm in ("A","B","AB"):
                path=endpoint(T4,n,h,s,arm)
                if path.exists(): four[n,h,s,arm]=checked(path,verify4)
    for arm in METHODS:
        for s in (1,2,3):
            path=T5/f"runs/s{s}_{arm}/1pct/timing.json"
            if path.exists(): five[arm,s]=checked(path,verify5)
    return four,five

def render(four,five):
    def row(*cols): return " & ".join(map(str,cols))+r"\\"
    def pair(a,b): return f"({a:.2f}, {b:.2f})"
    tex=[r"\documentclass[UTF8,zihao=-4,fontset=windows]{ctexart}",
         r"\usepackage[a4paper,margin=19mm]{geometry}\usepackage{booktabs,caption}",
         r"\pagestyle{empty}\setlength{\parindent}{0pt}\renewcommand{\arraystretch}{1.13}\begin{document}",
         r"\begin{center}{\Large 混合工艺实例的目标对照与组件消融}\end{center}",
         r"腔内非加工驻留上限为100\,s。$f_A$为产品返回工期，$f_B$计入产品等待与腔室节拍偏差。完整配置按三个种子取平均，空项待该配置的三个种子完成后填写。",
         r"\setcounter{table}{3}\begin{center}\captionof{table}{单目标与两阶段求解的目标值（10\%间隙）}\small",
         r"\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}ccccc@{}}\toprule",
         row("产品片数","清洁阈值 $H$","仅优化 $f_A$","仅优化 $f_B$","两阶段"),r"\midrule"]
    for n,h in TABLE4_CASES:
        vals=[]
        for arm in ("A","B","AB"):
            sample=[four[n,h,s,arm] for s in (1,2,3) if (n,h,s,arm) in four]
            vals.append(pair(*map(mean,zip(*sample))) if len(sample)==3 else "—")
        tex.append(row(n,h,*vals))
    tex.extend([r"\bottomrule\end{tabular*}\end{center}",
                r"表4各目标值写为 $(f_A,f_B)$，单位为秒。"])
    pairs=[(n,h,s) for n,h in TABLE4_CASES for s in (1,2,3) if (n,h,s,"AB") in four and
           sum((n,h,i,"AB") in four for i in (1,2,3))<3]
    if pairs:
        tex.extend([r"\begin{center}\small 已完成的逐种子配对\par",
                    r"\begin{tabular}{ccccc}\toprule",row("产品片数","$H$","种子","仅优化 $f_A$","两阶段"),r"\midrule"])
        for n,h,s in pairs: tex.append(row(n,h,s,pair(*four[n,h,s,"A"]),pair(*four[n,h,s,"AB"])))
        tex.append(r"\bottomrule\end{tabular}\end{center}")
    tex.extend([r"\begin{center}\captionof{table}{4片混合实例的选割策略与组件消融（$H=10$，两阶段间隙均为1\%）}\small",
                r"\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrrrrr@{}}\toprule",
                row("求解配置","最终 $f_A$","交接时 $f_B$","最终 $f_B$","累计耗时","选割次数"),r"\midrule"])
    for arm,label in zip(METHODS,LABELS):
        sample=[five[arm,s] for s in (1,2,3) if (arm,s) in five]
        tex.append(row(label,*([f"{mean(col):.2f}" for col in zip(*sample)] if len(sample)==3 else ["—"]*5)))
    tex.extend([r"\bottomrule\end{tabular*}\end{center}",
                r"表5的目标值与耗时均以秒计。累计耗时包括分层初始化、工期搜索和交接后的建模、求解及校验。选割次数为第一阶段进入选割的轮数。各配置共用经独立投影求得的397\,s全局工期下界；该下界的离线计算时间单列，不计入各配置耗时。",
                r"\par\smallskip 独立下界计算用时24.20\,s。",
                f"\\par\\smallskip 更新于{datetime.now():%Y-%m-%d %H:%M}。表4已核验{len(four)}/{TABLE4_TOTAL}项，表5已核验{len(five)}/15项。",
                r"\end{document}"])
    source="\n".join(tex)
    with tempfile.TemporaryDirectory() as tmp:
        draft=Path(tmp)/"Tables_CN.tex"
        draft.write_text(source,encoding="utf8")
        subprocess.run(["xelatex","-halt-on-error","-interaction=nonstopmode",draft.name],cwd=tmp,
                       stdout=subprocess.DEVNULL,check=True)
        for suffix in (".tex",".pdf"):
            dst=PAPER/("Tables_CN"+suffix)
            tmpdst=dst.with_suffix(suffix+".tmp")
            shutil.copyfile(draft.with_suffix(suffix),tmpdst)
            tmpdst.replace(dst)

def main(watch):
    PAPER.mkdir(parents=True,exist_ok=True)
    cachepath=PAPER/"verified.json"
    cache=read(cachepath) if cachepath.exists() else {}
    last=None
    while True:
        four,five=gather(cache)
        signature=(len(four),len(five),tuple((k,v[0]) for k,v in sorted(cache.items())))
        if signature!=last:
            try:
                render(four,five)
                write(cachepath,cache)
                print(f"Published table 4 {len(four)}/{TABLE4_TOTAL}, table 5 {len(five)}/15",flush=True)
                last=signature
            except PermissionError:
                if not watch: raise
                print("Output file is open for exclusive access. Retrying.",flush=True)
        if not watch or (len(four)==TABLE4_TOTAL and (len(five)==15 or (T5/"superseded.json").exists()) and last==signature): break
        time.sleep(25)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--watch",action="store_true")
    main(parser.parse_args().watch)
