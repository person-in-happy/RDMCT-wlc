"""Draw figures exclusively from reviewed event data, without interpolating feasibility."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.ticker import MaxNLocator
from pathlib import Path
from review import OUT, REPORT, S1, SEEDS, METHODS, read, rows

FIG = REPORT/"figures"
COLORS=("#00655d","#d16935","#3f71a0","#818894")


def finish(fig,name):
    fig.savefig(FIG/(name+".pdf"),bbox_inches="tight",pad_inches=.06)
    fig.savefig(FIG/(name+".png"),bbox_inches="tight",pad_inches=.06,dpi=200)
    plt.close(fig)


def style(ax):
    ax.grid(True,color="#d9e1e3",lw=.5,zorder=0)
    ax.spines[["right","top"]].set_visible(False)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.tick_params(labelsize=9)


def draw():
    info=read(REPORT/"verified.json")
    FIG.mkdir(exist_ok=True)
    chinese=Path("C:/Windows/Fonts/msyh.ttc")
    fm.fontManager.addfont(str(chinese))
    plt.rcParams.update({"font.family":fm.FontProperties(fname=str(chinese)).get_name(),
                         "font.size":10,"pdf.fonttype":42,"axes.unicode_minus":False,
                         "axes.labelcolor":"#223337","xtick.color":"#344549","ytick.color":"#344549"})
    fig,(left,right)=plt.subplots(1,2,figsize=(7.5,2.65),gridspec_kw={"width_ratios":[1,1.03]})
    exact=rows(S1/"front_checked.csv")
    for ax,subset in ((left,exact[:3]),(right,exact[3:])):
        for r in subset:
            a,b=float(r["certified_A"]),float(r["certified_B"])
            unsupported=r["unsupported"]=="True"
            ax.scatter(a,b,s=32,marker="D" if unsupported else "o",
                       color=COLORS[1] if unsupported else COLORS[0],zorder=3)
            ax.annotate(f"({a:.0f}, {b:.2f})" if a<400 else f"({a:.0f}, {b:.0f})",
                        (a,b),xytext=(3,6),textcoords="offset points",fontsize=8)
        ax.set_xlabel("产品完工时间 A（s）")
        style(ax)
    left.set(xlim=(329,344),ylim=(119,151),ylabel="等待与节拍指标 B（加权秒）")
    right.set(xlim=(513,521.8),ylim=(31,101))
    right.set_xticks([514,516,518,520])
    left.set_title("（a）两片产品同对",loc="left",fontsize=10)
    right.set_title("（b）每片产品各与一片辅助片配对",loc="left",fontsize=10)
    from matplotlib.lines import Line2D
    fig.legend(handles=[Line2D([],[],marker="o",ls="",color=COLORS[0],label="支持点"),
                        Line2D([],[],marker="D",ls="",color=COLORS[1],label="非支持点")],
               loc="lower center",ncol=2,frameon=False,fontsize=9,bbox_to_anchor=(.5,-.02))
    fig.subplots_adjust(left=.085,right=.98,top=.89,bottom=.31,wspace=.25)
    finish(fig,"pareto_s1")
    fig,(left,right)=plt.subplots(1,2,figsize=(7.85,3.25),gridspec_kw={"width_ratios":[1.42,1]})
    names=("领域搜索","NSGA-II","MOEA/D","固定结构扫描")
    for i,method in enumerate(METHODS):
        submitted=set()
        for seed in SEEDS:
            submitted.update((x["a"],x["b"]) for x in read(OUT/f"{method}_{seed}"/"run.json")["archive"])
        a,b=zip(*sorted(submitted))
        left.scatter(a,b,s=23,facecolor="none",edgecolor=COLORS[i],marker=("o","s","^","D")[i],
                     alpha=.82,lw=.85,label=names[i],zorder=2)
    all_points=[(float(v["A"]),float(v["B"])) for v in rows(REPORT/"front75.csv")]
    xs,ys=zip(*all_points)
    left.scatter(xs,ys,c="#142f3a",marker="o",s=12,zorder=4,label="合并非支配点")
    left.scatter(*info["warm"],c="#97375b",marker="*",s=80,zorder=5,label="共同起点")
    left.set_title("（a）全部提交点与经验前沿",loc="left",fontsize=10)
    left.set(ylabel="等待与节拍指标 B（加权秒）",xlabel="产品完工时间 A（s）")
    left.xaxis.set_major_locator(MaxNLocator(nbins=5,integer=True))
    short=[(a,b) for a,b in all_points if a<=min(xs)+4]
    right.scatter(*zip(*short),c="#142f3a",s=18,zorder=4)
    right.set_title(f"（b）最短工期附近的 {len(short)} 个发现点",loc="left",fontsize=10)
    right.set(xlabel="产品完工时间 A（s）")
    right.xaxis.set_major_locator(MaxNLocator(nbins=4,integer=True))
    right.ticklabel_format(useOffset=False,axis="x")
    for ax in (left,right):
        style(ax)
    fig.legend(*left.get_legend_handles_labels(),loc="lower center",ncol=3,frameon=False,fontsize=8,
               columnspacing=1.2,bbox_to_anchor=(.5,-.025))
    fig.subplots_adjust(left=.10,right=.985,top=.90,bottom=.33,wspace=.23)
    finish(fig,"pareto_75")


if __name__=="__main__":
    draw()
