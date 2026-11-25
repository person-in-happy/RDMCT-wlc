"""Compare the native quadratic runs with the independently certified short arc."""
import csv
from fractions import Fraction
from pathlib import Path
import os
import sys
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager,pyplot as plt

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from solver import read,save,sha,cell
from score import metrics
sys.path.insert(0,str(cell.BACKENDS["D"]))
from validate import validate

ROOT=HERE.parents[3]
BASE=ROOT/"JMS-version/results/residence_objective_20261125"
OUT=BASE/"preference_review/quadratic_native"
Q=BASE/"preference_review/quadratic_certificate.json"
LINE=BASE/"best_reuse/continuous_frontier/certificate.json"

def main():
    proof=read(Q); linear=read(LINE)
    arc=proof["short_arc"]; assert arc["t"]==[0,.875] and proof["tau_seconds"]==1
    cases=[]
    for d in sorted(OUT.glob("H*_cap*")):
        src=d/"result.json"
        r=read(src)
        for n,h in r["files"].items():assert sha(d/n)==h
        assert r["native_status"]=="optimal" and r["native_rows"]==281012 and r["physical_replay"]["valid"]
        s=read(d/"schedule.json")
        assert validate(s)["valid"]
        m=metrics(s); square=m["mean_residence"]+m["residence_range"]**2+m["clean_deficit"]
        cap=Fraction(r["settings"]["cap"]); t=min(cap-553,Fraction(7,8))
        exact=Fraction(17,4)-Fraction(7,4)*t+t*t
        assert abs(square-float(exact))<1e-7 and abs(square-r["physical_objective"])<1e-10
        cases.append(dict(H=r["settings"]["H"],cap=float(cap),C=m["cmax"],mean=m["mean_residence"],D=m["residence_range"],
            E=m["clean_deficit"],quadratic_score=square,exact_conditional_score=str(exact),solver_conditional_LB=r["native_dual"],
            solver_conditional_UB=r["native_primal"],native_gap=r["native_absolute_gap"],score_minus_exact=square-float(exact),
            exact_minimizer_earliest_C=float(553+t),physical_minus_expected_C=m["cmax"]-float(553+t),
            record=src.relative_to(ROOT).as_posix(),sha256=sha(src)))
    cases.sort(key=lambda r:(r["H"],r["cap"]))
    assert len(cases)==12 and {r["H"] for r in cases}=={3,10}
    with (OUT/"quadratic_bounds.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(cases[0]));writer.writeheader();writer.writerows(cases)
    long=BASE/"preference_review/n8_H10_quadratic"
    ref=read(long/"primary.json")
    assert sha(long/"primary.json")==proof["source_sha256"]["H10_endpoint"]
    s=read(long/"schedule.json")
    assert validate(s)["valid"] and sha(long/"schedule.json")==ref["schedule_sha256"] and sha(long/"assignment.json.gz")==ref["assignment_sha256"]
    f=metrics(s);assert abs(f["mean_residence"]+f["residence_range"]**2+f["clean_deficit"]-proof["unrestricted_H10_minimum"])<1e-9
    actual={}
    for r in cases:
        actual.setdefault(r["cap"],[]).append([r["C"],r["quadratic_score"]])
    for points in actual.values():assert len(points)==2 and max(abs(a-b) for a,b in zip(*points))<.0002
    os.environ["SOURCE_DATE_EPOCH"]="0"
    family=font_manager.FontProperties(family=["Microsoft YaHei","SimHei"])
    font=font_manager.FontProperties(fname=font_manager.findfont(family,fallback_to_default=False)).get_name()
    plt.rcParams.update({"font.family":"sans-serif","font.sans-serif":[font,"DejaVu Sans"],"font.size":8,
                         "pdf.fonttype":42,"mathtext.fontset":"dejavusans","axes.unicode_minus":False})
    fig,ax=plt.subplots(figsize=(5.10,3.08))
    fig.subplots_adjust(left=.125,right=.97,bottom=.20,top=.94)
    blue,orange="#275D82","#B45E24"
    a,b=linear["cmax_interval"]
    ax.plot([a,b],[linear["intercept"],linear["intercept"]+linear["slope"]*(b-a)],
            color=blue,lw=1.45,label="线性极差（三种清洁计分重合）",zorder=3)
    tt=[arc["t"][0]+(arc["t"][1]-arc["t"][0])*i/180 for i in range(181)]
    ax.plot([a+t for t in tt],[4.25-1.75*t+t*t for t in tt],color=orange,lw=1.7,
            label=r"二次极差（$\tau=1$ s）",zorder=3)
    # Each cap has one solution for each H. Overlay both original unrounded
    # coordinates; an interior arc ending at its minimum has no horizontal Pareto tail.
    ax.scatter([r["C"] for r in cases],[r["quadratic_score"] for r in cases],marker="D",s=19,
               facecolor="white",edgecolor=orange,linewidths=.9,zorder=5,label="原模型二次优化结果")
    ax.annotate("短窗最低点\n(553.875, 3.484375)",
                xy=(arc["terminal_C"],arc["terminal_Rq"]),xytext=(553.69,3.367),ha="right",va="center",fontsize=7.45,
                color="#374750",arrowprops=dict(arrowstyle="->",color="#57616A",lw=.65,shrinkB=3,shrinkA=2))
    ax.set_xlim(552.969,554.032);ax.set_ylim(3.275,4.32)
    ax.set_xticks((553,553.25,553.5,553.75,554),("553","553.25","553.5","553.75","554"))
    ax.set_yticks((3.5,3.75,4,4.25),("3.50","3.75","4.00","4.25"))
    ax.set_xlabel(r"实际工期 $f_A$ / s",fontsize=8.4,labelpad=4)
    ax.set_ylabel("工艺目标 / 等效 s",fontsize=8.4,labelpad=5)
    ax.tick_params(labelsize=7.7,length=3,width=.6)
    ax.grid(axis="y",lw=.5,color="#E0E3E8",zorder=0)
    ax.spines[["right","top"]].set_visible(False)
    for k in ("left","bottom"):ax.spines[k].set(color="#5B626A",linewidth=.65)
    ax.legend(loc="upper right",frameon=True,facecolor="white",edgecolor="none",framealpha=1,fontsize=7.55,
              borderaxespad=.1,handlelength=2,handletextpad=.5,labelspacing=.4)
    pdf=OUT/"fig_quadratic_objective_comparison_cn.pdf"
    fig.savefig(pdf,metadata={"Title":"Residence objectives over the certified short makespan window","Creator":"Matplotlib; independently solved native convex objective and exact frontier certificates"})
    plt.close(fig)
    save(OUT/"comparison_evidence.json",dict(figure=pdf.relative_to(ROOT).as_posix(),figure_sha256=sha(pdf),
        report_source=sha(Path(__file__)),linear_certificate=sha(LINE),quadratic_certificate=sha(Q),
        squared_score="mean + D^2/(1 s) + gamma E; gamma=1 s/cycle",linear_coincident=["mean + D + gamma E","mean + D","(mean+D)*(1 + penalty_per_cycle*E)"],
        plotted_scope="Realized C within [553,554] for both 8-wafer inputs; segment/arc only, with actual QCP witnesses. The cap at 554 permits earlier completion.",
        chart_records=cases,csv_sha256=sha(OUT/"quadratic_bounds.csv"),temporal_error_largest_s=max(abs(r["physical_minus_expected_C"]) for r in cases),
        objective_error_largest_s=max(abs(r["score_minus_exact"]) for r in cases),maximum_native_gap=max(r["native_gap"] for r in cases),
        unrestricted_H3_score=proof["unrestricted_H3_minimum"],unrestricted_H10_score=proof["unrestricted_H10_minimum"],
        unrestricted_H10_verified_C=f["cmax"],unrestricted_H10_source=(long/"primary.json").relative_to(ROOT).as_posix(),
        unrestricted_H10_source_sha256=sha(long/"primary.json"),separation="No claim of a fully mapped long-time H10 frontier between 553.875 and 1100.8125."))
    print("Verified",len(cases),"native endpoints, max score difference",
          max(abs(r["score_minus_exact"]) for r in cases),"; max makespan difference(s)",max(abs(r["physical_minus_expected_C"]) for r in cases))

if __name__=="__main__":main()
