"""Collect native H=10 epsilon runs and plot exact four/eight frontiers plus the observed sixteen frontier."""
import csv
from pathlib import Path
import sys
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
from sweep import OUT,R,HUB,MIX,JMS,atomic,metrics,read,sha,validate

DEST=JMS/"figures/rolling_refinement_20261119/fig_pareto_scales_huber_cn.pdf"
BLUE="#20598a"
ORANGE="#b65d22"


def get_info(path,record=None):
    target=path/"schedule.json"
    doc=read(target)
    native=read(record or path/"result.json")
    stored=native.get("schedule_sha256") or native["files"]["schedule.json"]
    assert sha(target)==stored
    q=validate(doc);assert q["valid"] and q["product_return_cmax"]>0
    score=metrics(doc)
    assert abs(q["product_return_cmax"]-score["cmax"])<2e-5
    original=native.get("rows",native.get("original_rows",native.get("replayed_rows",0)))
    assert original>0
    return dict(schedule=target.relative_to(JMS).as_posix(),sha256=stored,rows=original,checks=q["checks"],**score),doc["config"]


def samples():
    cfg=read(MIX/"input.json")["config"]
    folders=[p.parent for p in OUT.glob("sixteen*/*/schedule.json")]
    folders.extend(p.parent for p in OUT.glob("cap*/p*_native/schedule.json"))
    folders.extend((OUT/"two_blocks",MIX/"prepared"))
    folders.extend(p.parent for p in MIX.glob("witnesses/*/schedule.json"))
    folders.extend(p.parent for p in MIX.glob("grid/*/*/schedule.json"))
    base=R/"table4_extended16_20261125/H10"
    folders.extend(p.parent for p in base.rglob("schedule.json"))
    points=[]
    for path in sorted(set(folders)):
        q=path/"result.json"
        if not q.exists():q=path/"primary.json"
        if not q.exists():continue
        native=read(q)
        if not(native.get("schedule_sha256") or "schedule.json" in native.get("files",{})):continue
        point,config=get_info(path,q)
        assert cfg==config,(path,"mismatched input")
        points.append(point)
    ranks={}
    for pt in points:
        score=tuple(round(pt[k],4) for k in ("cmax","secondary"))
        ranks.setdefault(score,pt)
    front=[];best=float("inf")
    for (_,b),point in sorted(ranks.items()):
        if b<best:
            front.append(point);best=b
    return points,front


def across_break(ax,right):
    ax.spines["right"].set_visible(False);right.spines["left"].set_visible(False)
    right.tick_params(left=False,labelleft=False)
    kw=dict(marker=[(-1,-.8),(1,.8)],markersize=5,linestyle="none",color="#333333",mec="#333333",mew=.62,clip_on=False)
    ax.plot([1],[0],transform=ax.transAxes,**kw);right.plot([0],[0],transform=right.transAxes,**kw)


def plot(front,certified):
    mpl.rcParams.update({"font.sans-serif":["Microsoft YaHei","DejaVu Sans"],"axes.unicode_minus":False,
        "font.size":8.1,"axes.linewidth":.7,"pdf.fonttype":42,"mathtext.fontset":"stix","xtick.labelsize":7.5,"ytick.labelsize":7.5})
    fig=plt.figure(figsize=(7.25,2.43))
    gs=fig.add_gridspec(1,3,width_ratios=(.76,1.25,1.31),left=.085,right=.986,bottom=.245,top=.80,wspace=.38)
    aa=fig.add_subplot(gs[0,0])
    sb=gs[0,1].subgridspec(1,2,width_ratios=(4,1.25),wspace=.2)
    ab=fig.add_subplot(sb[0]);abr=fig.add_subplot(sb[1],sharey=ab)
    sc=gs[0,2].subgridspec(1,2,width_ratios=(1,1.12),wspace=.19)
    ac=fig.add_subplot(sc[0]);acr=fig.add_subplot(sc[1],sharey=ac)
    for ax in (aa,ab,abr,ac,acr):
        ax.spines[["right","top"]].set_visible(False);ax.tick_params(direction="out",length=2.6,width=.65,pad=2.4)
        ax.grid(axis="y",color="#e8ebef",linewidth=.55)
    for a,z in ((ab,abr),(ac,acr)):across_break(a,z)
    aa.plot([397,417],[3.5,3.46875],"o",ms=4.2,color=BLUE)
    aa.set(xlim=(393.5,420.5),ylim=(3.463,3.505),xticks=(397,417),yticks=(3.47,3.48,3.49,3.50))
    aa.set_ylabel(r"工艺目标 $f_B$（等效 s）",labelpad=4)
    t=np.linspace(0,.75,200)
    ab.plot(553+t,3.75-.75*t+.5*t*t,color=BLUE,linewidth=1.6)
    ab.plot([553,553.75],[3.75,3.46875],"o",ms=3.2,color=BLUE)
    abr.plot(576.625,3.4296875,marker="D",ms=4,color=ORANGE)
    abr.annotate(r"$H=10$",(576.625,3.4296875),xytext=(-1,9),textcoords="offset points",
                 ha="center",color=ORANGE,fontsize=7.3)
    ab.set(xlim=(552.96,553.79),ylim=(3.40,3.78),xticks=(553,553.375,553.75),yticks=(3.45,3.55,3.65,3.75))
    ab.set_xticklabels(("553","553.375","553.75"))
    abr.set(xlim=(576.1,577.1),xticks=(576.625,));abr.set_xticklabels(("576.625",))
    for a,subset in ((ac,[p for p in front if p["cmax"]<=812]),(acr,[p for p in front if p["cmax"]>812])):
        a.plot([p["cmax"] for p in subset],[p["secondary"] for p in subset],linestyle="none",marker="o",ms=3.5,mew=.85,mfc="white",mec=BLUE,clip_on=False)
    ac.plot([x for x,y in certified],[y for x,y in certified],linestyle="-",linewidth=1.3,marker="o",ms=3.7,color=BLUE)
    ac.set(xlim=(809.84,812.25),xticks=(810,811,812),ylim=(-.4,41),yticks=(0,10,20,30,40))
    last=max(p["cmax"] for p in front)
    hi=max(820,last+40)
    ticks=[900,1200,1450] if last>=1300 else [850,1000,1150]
    acr.set(xlim=(813,hi),xticks=[s for s in ticks if s<hi])
    for y,fill,label in ((.91,BLUE,"已证"),(.76,"white","近似")):
        acr.plot(.11,y,marker="o",ms=3.6,mew=.85,mfc=fill,mec=BLUE,transform=acr.transAxes,clip_on=False)
        acr.text(.29,y,label,transform=acr.transAxes,fontsize=7.3,va="center")
    for left,right,head in ((aa,aa,"(a)  4 片，$H=3,10$"),(ab,abr,"(b)  8 片，$H=3,10$"),(ac,acr,"(c)  16 片，$H=10$")):
        center=(left.get_position().x0+right.get_position().x1)/2
        fig.text(center,.9,head,ha="center",va="center",fontsize=9)
        fig.text(center,.07,r"工期 $f_A$（s）",ha="center",va="center",fontsize=8.3)
    fig.savefig(DEST,metadata={"Title":"混合工艺实例的工期与工艺目标前沿"})
    plt.close(fig)


def main():
    points,front=samples()
    four={}
    for h in (3,10):
        pair=[]
        for tag in ("short397","417_pinned"):
            d,_=get_info(OUT/f"four_native_H{h}"/tag);pair.append(d)
        assert [(d["cmax"],d["secondary"]) for d in pair]==[(397.,3.5),(417.,3.46875)]
        four[str(h)]=pair
    bounds=[read(OUT/"four_bound"/f"{side}_0.json") for side in (2,3)]
    assert all(item["status"]=="OPTIMAL" for item in bounds) and [item["lower"] for item in bounds]==[417,447]
    eight=HUB/"frontier/certificate.json"
    n8=read(eight)
    assert n8["H3_complete_frontier"] and n8["H10_attainment"]["lower"]==576.625
    assert read(R/"table3_grid16_20261125/ranked/mixed_809/summary.json")["lower"]==810
    assert front[0]["cmax"]==810 and abs(front[-1]["secondary"]-3.404296875)<2e-6
    for name,items in (("all_observations.csv",points),("sixteen_pareto.csv",front)):
        with (OUT/name).open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
    proof = read(OUT/"cap810/p0020.json")
    continuum=read(OUT/"continuous16/certificate.json")
    assert continuum["interval"]==[810,811]
    certified=[(810,37.125),(811,36.)]
    assert proof["status"]=="OPTIMAL" and proof["lower16"]/16==certified[0][1]
    assert abs(front[0]["secondary"]-certified[0][1])<1e-6
    remaining=read(OUT/"cap812/catalogue.json")["remaining"]
    assert len(remaining)==6
    bounds={i:read(OUT/f"cap812/p{i:04}.json") for i in remaining}
    assert all(d["status"]=="INFEASIBLE" for i,d in bounds.items() if i not in (20,26))
    assert bounds[20]["lower16"]/16==31.75
    stronger=read(OUT/"cap812/support_0_1/result.json")
    assert stronger["status"]=="OPTIMAL" and stronger["lower"]==22.3125
    between=[p["secondary"] for p in front if abs(p["cmax"]-812)<1e-6]
    assert len(between)==1 and abs(between[0]-23.25)<1e-6
    plot(front,certified)
    results=dict(four_endpoints=four,four_proof="four_bound/proof.md",four_lower_by_first_product=[417,447],
        eight_proof=eight.relative_to(JMS).as_posix(),eight_sha256=sha(eight),sixteen_samples=len(points),sixteen_distinct_schedules=len({p["sha256"] for p in points}),
        sixteen_epsilon_cells=len(list(OUT.glob("sixteen*/cap_*/result.json"))),sixteen_pareto_points=len(front),
        sixteen_scope="Nondominated among all recorded schedules; epsilon solves on a finite set of original resource orders",
        sixteen_global_minimum_C=810,sixteen_global_minimum_B=3.404296875,sixteen_cross_structure_points=certified,
        sixteen_cross_structure_proof="cap810/proof.md",sixteen_continuous_certificate="continuous16/certificate.json",
        sixteen_continuous_interval=continuum["interval"],sixteen_continuous_curve=continuum["formula"],
        cap812_global_B_bounds=[22.3125,23.25],cap812_drop_at_least=8.5,
        records_sha256=sha(OUT/"all_observations.csv"),sixteen_nondominated_sha256=sha(OUT/"sixteen_pareto.csv"),
        figure=DEST.relative_to(JMS).as_posix(),figure_sha256=sha(DEST))
    atomic(OUT/"validation.json",results)
    print(results["sixteen_samples"],results["sixteen_epsilon_cells"],results["sixteen_pareto_points"],flush=True)


if __name__=="__main__":
    main()
