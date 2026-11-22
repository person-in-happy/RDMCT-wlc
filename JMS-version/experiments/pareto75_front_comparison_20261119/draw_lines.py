"""Draw stepwise deadline envelopes and empirical attainment, with explicit method membership."""
import itertools
from pathlib import Path
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from analysis_fronts import (HERE,OUT,OLD,OLD_OUT,OLD_REVIEW,REPORT,CASES,METHODS,SEEDS,NAMES,
                             csvrows,nd,read,step_at_least_half)
from case_setup import PARETO

FIG=REPORT/"figures"
STYLES={"domain":("#00705b","-","o",2.1), "uniform":("#a24d96",(0,(1.5,2)),"P",1.7),
        "nsga2":("#d35e13",(0,(6,2.4)),"s",1.75), "moead":("#2064a4",(0,(7,2,1.6,2)),"^",1.8),
        "fixed":("#696d70",(0,(3,2)),"D",1.5), "pooled":("#15191d",(0,(1,2)),".",1.2),
        "full":("#00705b","-","o",2.2),"supported":("#be5c28",(0,(5,2.4)),"s",1.6),
        "rl_domain":("#a24d96",(0,(1.5,2)),"P",1.7),"epsilon":("#73787c",(0,(2,1,2,3)),"D",1.5),
        "legacy":("#735f32",(0,(8,2,2,2,2,2)),"x",1.5)}
ORDER=("domain","nsga2","moead","uniform")
LABEL={**NAMES,"pooled":"全部发现的合并边界","full":"全部认证点","supported":"仅线性加权支持点",
       "rl_domain":"领域搜索＋学习选割","epsilon":"ε-SCIP","legacy":"原两阶段"}
CASE_LABEL={"mix37":"37 片并行配方＋38 片链式配方","mix50":"50 片并行配方＋25 片链式配方"}


def setup():
    FIG.mkdir(parents=True,exist_ok=True)
    font=Path("C:/Windows/Fonts/msyh.ttc")
    fm.fontManager.addfont(str(font))
    plt.rcParams.update({"font.family":fm.FontProperties(fname=str(font)).get_name(),"font.size":10.0,
        "axes.unicode_minus":False,"pdf.fonttype":42,"axes.labelcolor":"#263338","xtick.color":"#263338",
        "ytick.color":"#263338","axes.edgecolor":"#637075","lines.solid_capstyle":"butt"})


def prettify(ax):
    ax.grid(color="#dde5e6",lw=.65,zorder=0)
    ax.spines[["top","right"]].set_visible(False)
    ax.ticklabel_format(useOffset=False,axis="both")
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5,integer=True))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5,integer=True))
    ax.tick_params(labelsize=8.6)


def steps(ax,points,style,right,marked=True):
    p=nd(points)
    if not p:
        return
    color,ls,mark,lw=STYLES[style]
    x,y=map(list,zip(*p))
    if right>x[-1]:
        x.append(right);y.append(y[-1])
    ax.step(x,y,where="post",color=color,ls=ls,lw=lw,zorder=2)
    if marked:
        ax.plot(*zip(*p),ls="",marker=mark,ms=4.4,mec=color,mew=1.05,
                mfc="none" if style not in ("pooled","full") else color,zorder=4)


def legend(fig,styles,cols,anchor=-.004):
    handles=[Line2D([0],[0],c=STYLES[k][0],ls=STYLES[k][1],lw=STYLES[k][3],marker=STYLES[k][2],
                    ms=4.8,mfc="white",label=LABEL[k]) for k in styles]
    fig.legend(handles=handles,loc="lower center",bbox_to_anchor=(.5,anchor),frameon=False,
               ncol=cols,handlelength=3.6,columnspacing=1.25,fontsize=9.0)


def finish(fig,stem):
    fig.savefig(FIG/(stem+".pdf"),bbox_inches="tight",pad_inches=.075)
    fig.savefig(FIG/(stem+".png"),bbox_inches="tight",pad_inches=.075,dpi=210)
    plt.close(fig)


def prior_figures():
    exact=csvrows(PARETO/"runs/s1_refine01/front_checked.csv")
    all_s1=[(float(r["certified_A"]),float(r["certified_B"])) for r in exact]
    supported=[p for p,r in zip(all_s1,exact) if r["unsupported"]=="False"]
    unsupported=[p for p,r in zip(all_s1,exact) if r["unsupported"]=="True"]
    fig,axs=plt.subplots(1,2,figsize=(7.75,2.95),gridspec_kw={"width_ratios":[1.23,1]})
    for ax,(lo,hi),ylim,title in zip(axs,((324,526),(512.7,520.2)),((32,153),(30,133)),
            ("（a）七个认证点与支持点","（b）非支持点所在区间")):
        steps(ax,all_s1,"full",hi)
        steps(ax,supported,"supported",hi)
        ax.scatter(*zip(*unsupported),s=36,marker="D",facecolors="#00705b",edgecolors="white",zorder=5)
        ax.set(xlim=(lo,hi),ylim=ylim,xlabel="交付期限 A（s）")
        ax.set_title(title,loc="left",fontsize=10)
        prettify(ax)
    axs[0].set_ylabel("期限内最低 B（加权秒）")
    axs[1].axhline(100,color="#849093",lw=.9,ls=":")
    axs[1].text(513.0,102,"B = 100",fontsize=8,color="#535d60")
    for a,b in unsupported+[(519,42)]:
        axs[1].annotate(f"{int(a)}, {int(b)}",(a,b),xytext=(3,-11 if a in (514,517) else 6),
                        textcoords="offset points",fontsize=7.3)
    fig.subplots_adjust(left=.095,right=.985,bottom=.29,top=.90,wspace=.26)
    legend(fig,("full","supported"),2)
    finish(fig,"pareto_s1")

    styles=("domain","nsga2","moead","fixed")
    union={m:nd((x["a"],x["b"]) for s in (1,2,3) for x in read(OLD_OUT/f"{m}_{s}"/"run.json")["archive"]) for m in styles}
    overall=[(float(r["A"]),float(r["B"])) for r in csvrows(OLD_REVIEW/"front75.csv")]
    fig,axs=plt.subplots(1,2,figsize=(8.1,3.05),gridspec_kw={"width_ratios":[1.02,1.12]})
    for ax,span,vrange,title in zip(axs,((7500,8920),(7548,8075)),((1630,4070),(1740,2650)),
              ("（a）四种方法的三种子提交前沿","（b）结构搜索覆盖的交付区间")):
        for m in styles:
            steps(ax,union[m],m,span[1])
        if ax is axs[1]:
            steps(ax,overall,"pooled",span[1])
        ax.set(xlim=span,ylim=vrange,xlabel="交付期限 A（s）")
        ax.set_title(title,loc="left",fontsize=10)
        prettify(ax)
    axs[0].set_ylabel("期限内最低 B（加权秒）")
    fig.subplots_adjust(left=.09,right=.986,bottom=.30,top=.91,wspace=.23)
    legend(fig,(*styles,"pooled"),5)
    finish(fig,"pareto_75")


def limits(groups):
    all_p=[p for f in groups for p in f]
    x0=min(a for a,b in all_p);x1=max(a for a,b in all_p)
    y0=min(b for a,b in all_p);y1=max(b for a,b in all_p)
    return ((x0-.035*max(1,x1-x0),x1+.045*max(1,x1-x0)),
            (y0-.08*max(1,y1-y0),y1+.08*max(1,y1-y0)))


def new_figures():
    assert (REPORT/"verified.json").is_file()
    submitted={(c,m,s):nd((r["a"],r["b"]) for r in read(OUT/c/f"{m}_{s}"/"run.json")["archive"] if r["submitted"])
               for c in CASES for m in ORDER for s in SEEDS}
    fig,axes=plt.subplots(2,2,figsize=(8.3,5.45))
    for col,c in enumerate(CASES):
        typical={m:step_at_least_half([submitted[c,m,s] for s in SEEDS]) for m in ORDER}
        panels=({m:submitted[c,m,101] for m in ORDER},typical)
        # Use shared limits within each workload. Extreme late low-B solutions
        # appear in the single-run supplement as well as in the witness table.
        xlim,ylim=limits([f for panel in panels for f in panel.values()])
        for row,panel in enumerate(panels):
            ax=axes[row,col]
            for m in ORDER:
                steps(ax,panel[m],m,xlim[1],marked=row==0)
            ax.set(xlim=xlim,ylim=ylim)
            prettify(ax)
            if row==0:
                ax.set_title(CASE_LABEL[c],fontsize=10.3)
            else:
                ax.set_xlabel("交付期限 A（s）")
    axes[0,0].set_ylabel("种子 101 的最低 B（加权秒）",fontsize=9)
    axes[1,0].set_ylabel("至少半数运行达到的 B（加权秒）",fontsize=9)
    fig.subplots_adjust(left=.103,right=.985,top=.94,bottom=.15,hspace=.23,wspace=.20)
    legend(fig,ORDER,4)
    finish(fig,"paired75_lines")

    for c in CASES:
        fig,axgrid=plt.subplots(3,4,figsize=(12.2,7.25),sharex=True,sharey=True)
        xs,ys=limits([submitted[c,m,s] for s in SEEDS for m in ORDER])
        for ax,s in zip(axgrid.flat,SEEDS):
            for m in ORDER:
                steps(ax,submitted[c,m,s],m,xs[1])
            ax.set(xlim=xs,ylim=ys)
            ax.set_title(f"种子 {s}",loc="left",fontsize=9)
            prettify(ax)
        for ax in axgrid[-1,:]:
            ax.set_xlabel("交付期限 A（s）",fontsize=9)
        for ax in axgrid[:,0]:
            ax.set_ylabel("最低 B（加权秒）",fontsize=9)
        fig.subplots_adjust(left=.075,right=.99,top=.96,bottom=.13,hspace=.29,wspace=.17)
        legend(fig,ORDER,4)
        finish(fig,"all_seeds_"+c)


def small_figures():
    source=PARETO/"runs/formal02/evaluation"
    rr=csvrows(source/"points.csv")
    methods=("domain","rl_domain","nsga2","moead","epsilon","legacy")
    fig,axs=plt.subplots(2,2,figsize=(8.0,5.5))
    for ax,c in zip(axs.flat,("M4","H4","H8","H16")):
        group={m:nd((round(float(r["A"]),5),round(float(r["B"]),5)) for r in rr if
                    (r["suite"],r["case"],r["method"],r["seed"])==("main",c,m,"1")) for m in methods}
        xs,ys=limits(group.values())
        for m in methods:
            steps(ax,group[m],m,xs[1])
        ax.set(xlim=xs,ylim=ys,xlabel="交付期限 A（s）",ylabel="最低 B（加权秒）")
        ax.set_title(c+"，种子 1",loc="left",fontsize=10)
        prettify(ax)
    fig.subplots_adjust(left=.10,right=.98,bottom=.22,top=.94,wspace=.25,hspace=.45)
    legend(fig,methods,3)
    finish(fig,"small_fronts")


if __name__=="__main__":
    setup()
    prior_figures()
    small_figures()
    if "--historical" not in sys.argv:
        new_figures()
