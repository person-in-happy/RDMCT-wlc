"""Score the specialized S1 rerun against its independent certificate and plot the actual witnesses."""
import argparse
import gzip
from pathlib import Path
import json
from fractions import Fraction

from common import TOL, config, digest, metrics, save
from evaluate import reference, hits, hv, igdplus, write_csv
from native import Native
from validate import validate


def score(folder):
    run=json.loads((folder/"result.json").read_text(encoding="utf-8"))
    exact,unsupported=reference()
    coordinates=[]
    table=[]
    original=Native(config("S1"),1,25)
    try:
        for row in run["front"]:
            path=folder/row["schedule"]
            if digest(path)!=row["sha256"]:
                raise ValueError(f"Schedule hash changed for {path}")
            with gzip.open(path,"rt",encoding="utf-8") as f:
                d=json.load(f)
            check=validate(d)
            if not check["valid"] or not original.warm(d):
                raise ValueError(f"Independent original-model replay failed for {path}")
            m=metrics(d,25)
            xy=m["cmax"],m["secondary"]
            if max(abs(a-b) for a,b in zip(xy,row["ab"]))>TOL:
                raise ValueError("Archived coordinates changed")
            coordinates.append(xy)
            nearest=min(exact,key=lambda ab:max(abs(a-b) for a,b in zip(ab,xy)))
            err=max(abs(a-b) for a,b in zip(nearest,xy))
            table.append(dict(A=xy[0],B=xy[1],L_sum=m["wait_sum"],L_max=m["wait_max"],R=m["rhythm"],
                              certified_A=nearest[0],certified_B=nearest[1],coordinate_error=err,
                              matched=err<=TOL,unsupported=nearest in unsupported and err<=TOL,
                              archived_file=row["schedule"],sha256=row["sha256"],physical_checks=check["checks"],
                              full_original_variables=original.x.original_dimensions["variables"],
                              full_original_rows=original.x.original_dimensions["constraints"]))
    finally:
        original.close()
    bounds=((min(a for a,b in exact),max(a for a,b in exact)),(min(b for a,b in exact),max(b for a,b in exact)))
    result=dict(points=len(table),certified_hits=hits(coordinates,exact),unsupported_hits=hits(coordinates,unsupported),
                HV=hv(coordinates,bounds),certified_HV=hv(exact,bounds),IGD_plus=igdplus(coordinates,exact,bounds),
                A_at_B100=min(a for a,b in coordinates if b<=100+TOL),elapsed_two_stages=run["combined_seconds"],
                max_coordinate_error=max(r["coordinate_error"] for r in table),physical_and_full_original=True,
                profile="separate S1 topology-specific experiment, active-phase time plus event disjunction time")
    write_csv(folder/"front_checked.csv",table)
    save(folder/"independent_score.json",result)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family":["Microsoft YaHei","DejaVu Sans"],"axes.spines.top":False,
                         "axes.spines.right":False,"axes.unicode_minus":False,"savefig.dpi":200})
    fig,axes=plt.subplots(1,2,figsize=(10.6,4.4),layout="constrained")
    for ax,lims in zip(axes,((327,347,118,150),(511,525,35,105))):
        alo,ahi,blo,bhi=lims
        ax.scatter(*zip(*exact),s=110,facecolors="none",edgecolors="#1d242a",linewidths=1.25,
                   label="独立证书",zorder=3)
        for non,marker,color,label in ((False,"o","#167769","本次找回的支持点"),(True,"D","#b34c1b","本次找回的非支持点")):
            subset=[(r["A"],r["B"]) for r in table if r["unsupported"]==non]
            if subset:
                ax.scatter(*zip(*subset),s=32,marker=marker,color=color,label=label,zorder=4)
        for a,b in exact:
            if alo<a<ahi:
                label=f"({a:g}, {Fraction(b).limit_denominator(3)})"
                ax.annotate(label,(a,b),xytext=(6,7),textcoords="offset points",fontsize=9)
        ax.set(xlim=(alo,ahi),ylim=(blo,bhi),xlabel="产品完工时间 A（秒）",ylabel="等待与节拍指标 B（加权秒）")
        ax.grid(alpha=.16)
    axes[0].set_title("两片产品直接配对",loc="left",fontweight="bold")
    axes[1].set_title("每片产品各与一片辅助片配对",loc="left",fontweight="bold")
    axes[1].axhline(100,linestyle="--",color="#727986",linewidth=1)
    axes[1].text(524.7,100.7,"B = 100",ha="right",va="bottom",fontsize=8)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="outside lower center",ncol=3,frameon=False)
    fig.savefig(folder/"s1_complete_CN.png")
    plt.close(fig)
    print(f"已复验 {len(table)} 个排程，认证点 {result['certified_hits']}/7，非支持点 {result['unsupported_hits']}/3",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path)
    score(parser.parse_args().folder.resolve())
