"""Draw only continuous Pareto branches with physically verified schedules."""
import json

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pymupdf

from archive import JMS, OUT, RESULTS, read, sha

FIG = JMS / "figures/rolling_refinement_20261119/fig_pareto_extended_cn.pdf"
BLUE = "#19567a"
ORANGE = "#a54c20"


def branch(label, interval, func, scope="exact", left_open=False, right_open=False):
    return dict(label=label, low=float(interval[0]), high=float(interval[1]), func=func,
                scope=scope, left_open=left_open, right_open=right_open)


def clip_against_observations(curve, observations):
    """A decreasing reachable branch is dominated to the right of each superior observation up to their crossing."""
    lo, hi, score = curve["low"], curve["high"], curve["func"]
    cuts = []
    left_open, right_open = curve["left_open"], curve["right_open"]
    for row in observations:
        a,b = float(row["fA"]),float(row["fB"])
        c = max(a,lo)
        if a > hi + 1e-6:
            continue
        if a < lo-1e-6 and abs(b-score(lo))<2e-6:
            left_open = True
        if b >= score(c) - 2e-6:
            continue
        if c >= hi-1e-6:
            right_open = True
            continue
        end = hi
        if b > score(hi):
            l,h = c,hi
            for _ in range(52):
                mid = (l+h)/2
                if score(mid)>b:
                    l = mid
                else:
                    h = mid
            end = (l+h)/2
        if end > c+1e-8:
            cuts.append((c,end))
    cuts.sort()
    parts = []
    start = lo
    for a,b in cuts:
        if a > start+1e-7:
            parts.append(dict(curve, low=start, high=a, left_open=left_open, right_open=True))
        start = max(start,b)
        left_open = True
    if hi > start+1e-7:
        parts.append(dict(curve, low=start, high=hi, left_open=left_open, right_open=right_open))
    return parts


def branch_sets(observations):
    four_path = RESULTS/"pareto_four_enriched_20261125/pure4_certificate.json"
    base_path = RESULTS/"pareto_square_20261125/certificate.json"
    tail_path = RESULTS/"square_reverse16_20261125/continuous/proof.json"
    mid_path = RESULTS/"pareto_enriched_20261125/curves/families.json"
    short_path = OUT/"short16_family.json"
    four, base, tail, short = [read(p) for p in (four_path,base_path,tail_path,short_path)]
    middle = read(mid_path)["families"]["middle"]
    assert short["reachable_interval"] == [810,812] and short["certified_interval"] == [810,811]
    assert tail["native_rows"]==1109436 and tail["common_integer_vars"]==308924
    four_arcs = [
        [branch("4p_408", four["branch_408"]["interval"], lambda c:7-(409-c)/4+(409-c)**2/2, left_open=True)],
        [branch("4p_425", four["branch_425"]["interval"], lambda c:7-(426-c)/2+(426-c)**2/2, left_open=True)],
        [branch("4p_491", four["interval"], lambda c:7-3*(492-c)/4+(492-c)**2/2)]]
    e = base["eight"]
    eight_arcs = [
        [branch("8m_553", e["short_interval"], lambda c:3.75-.75*(c-553)+.5*(c-553)**2)],
        [branch("8m_576", e["tail_interval"], lambda c:3.625-.625*(c-576)+.5*(c-576)**2,left_open=True)]]
    def short_score(c):
        t = c-810
        return 457.625-30.125*t+.5*t*t
    short_curves = [branch("16m_810", [810,811], short_score)]
    short_curves += clip_against_observations(branch("16m_811", [811,812], short_score, "archive"), observations)
    assert middle["support"]["min_C_plus_2D"] == [875,875]
    mid_curve = branch("16m_873", [middle["C0"],middle["strictly_decreasing_until_C"]],
                       lambda c:3.4296875+(874.25-c)**2/8, "archive")
    mid_curves = clip_against_observations(mid_curve, observations)
    tail_curve = branch("16m_986", [986,987.125], lambda c:3.404296875+(987.125-c)**2/8, "archive")
    long_curves = clip_against_observations(tail_curve, observations)
    assert mid_curves and long_curves and short_curves[-1]["right_open"]
    rows = [four_arcs, eight_arcs, [short_curves, mid_curves, long_curves]]
    return rows, {p.relative_to(JMS).as_posix():sha(p) for p in (four_path,base_path,tail_path,short_path,mid_path)}


def draw(four, sixteen):
    groups, sources = branch_sets(sixteen)
    mpl.rcParams.update({"font.sans-serif":["Microsoft YaHei","DejaVu Sans"], "axes.unicode_minus":False,
                         "font.size":8, "axes.linewidth":.65, "pdf.fonttype":42, "mathtext.fontset":"stix",
                         "xtick.labelsize":7.4, "ytick.labelsize":7.4})
    fig = plt.figure(figsize=(7.15,4.95))
    grid = fig.add_gridspec(3,1, left=.092,right=.976,bottom=.105,top=.91,hspace=.82)
    heads = [r"(a) 4 片纯 $2\times2$，$H=10$", "(b) 8 片混合", r"(c) 16 片混合，$H=10$"]
    domains = {
        "4p_408":([408.5,408.625,408.75],[6.97,6.985,7]),
        "4p_425":([425.1,425.3,425.5],[6.875,6.92,6.965]),
        "4p_491":([491,491.125,491.25],[6.72,6.735,6.75]),
        "8m_553":([553,553.375,553.75],[3.47,3.60,3.75]),
        "8m_576":([576.35,576.5,576.625],[3.43,3.45,3.47]),
        "16m_810":([810,811,812],[400,428,458]),
        "16m_873":([873.55,873.9,874.25],[3.43,3.46,3.49]),
        "16m_986":([986.7,986.9,987.125],[3.405,3.415,3.425]),
    }
    manifest = []
    for row, panels in enumerate(groups):
        cols = grid[row].subgridspec(1,len(panels),wspace=.36 if len(panels)==3 else .27)
        axes = [fig.add_subplot(slot) for slot in cols]
        axes[0].set_ylabel(r"$f_B$（等效 s）",labelpad=2)
        left,right = axes[0].get_position(),axes[-1].get_position()
        fig.text((left.x0+right.x1)/2,left.y1+.022,heads[row],ha="center",va="bottom",fontsize=9.1)
        for col, (ax, curves) in enumerate(zip(axes,panels)):
            ax.spines[["top","right"]].set_visible(False)
            ax.tick_params(length=2.7,width=.65,pad=2)
            ax.grid(axis="y",color="#e6e9eb",lw=.5)
            for k in curves:
                xx = np.linspace(k["low"],k["high"],201)
                yy = k["func"](xx)
                assert np.all(np.diff(yy)<0),k["label"]
                color = BLUE if k["scope"]=="exact" else ORANGE
                ax.plot(xx,yy,lw=1.55,color=color,ls="-" if k["scope"]=="exact" else (0,(3.2,1.5)),
                        dash_capstyle="butt",solid_capstyle="butt")
                for is_open, x in ((k["left_open"],xx[0]),(k["right_open"],xx[-1])):
                    if is_open:
                        ax.plot(x,k["func"](x),ls="none",marker="o",mfc="white",mec=color,ms=3.2,mew=.8)
                manifest.append({**{field:value for field,value in k.items() if field!="func"},
                                 "low_score":float(yy[0]),"high_score":float(yy[-1])})
            label = curves[0]["label"]
            if label in domains:
                xt,yt = domains[label]
                ax.set_xticks(xt,labels=[f"{x:g}" if x==int(x) else f"{x:.3f}".rstrip("0") for x in xt])
                ax.set_yticks(yt,labels=[f"{y:.3f}".rstrip("0").rstrip(".") for y in yt])
            else:
                ax.xaxis.set_major_locator(mpl.ticker.MaxNLocator(4))
                ax.xaxis.set_major_formatter(mpl.ticker.FormatStrFormatter("%g"))
                ax.yaxis.set_major_locator(mpl.ticker.MaxNLocator(4))
                ax.yaxis.set_major_formatter(mpl.ticker.FormatStrFormatter("%g"))
            if row==1:
                ax.text(.98,.85,r"$H=3,10$" if col==0 else r"$H=10$",transform=ax.transAxes,ha="right",color=BLUE)
            if row==2:
                if col==0:
                    ax.axvline(811,lw=.5,color="#a1a8aa",ls=":",zorder=0)
                handles = [mpl.lines.Line2D([],[],color=BLUE,lw=1.45,label="已证前沿"),
                           mpl.lines.Line2D([],[],color=ORANGE,lw=1.45,ls="--",label="近似前沿")]
                if col==0:
                    ax.legend(handles=handles,frameon=False,loc="upper right",fontsize=6.8,
                              handlelength=1.9,borderaxespad=.16,handletextpad=.45)
            ax.margins(x=.045,y=.115)
    fig.text(.535,.015,r"完工时间 $f_A$（s）",ha="center",va="bottom",fontsize=8.8)
    fig.savefig(FIG,metadata={"Title":"不同批量的连续Pareto前沿","CreationDate":None,"ModDate":None})
    plt.close(fig)
    with pymupdf.open(FIG) as pdf:
        pdf[0].get_pixmap(matrix=pymupdf.Matrix(2.4,2.4),alpha=False).save(OUT/"preview.png")
    (OUT/"displayed_curves.json").write_text(json.dumps(dict(curves=manifest,source_hashes=sources,
        open_symbols="excluded mathematical endpoints only", isolated_observations_drawn=0),indent=2),encoding="utf8")
