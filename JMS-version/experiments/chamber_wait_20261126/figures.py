"""Render the verified candidates and compare chamber waiting with internal empty gaps."""
from pathlib import Path
import sys
import subprocess
from unittest.mock import patch

from run import CASES,JMS,sha,profile,write,cell,validate
from current_defaults_swimlane import build,STYLE
import render_huber_gantt_cn as gantt
from matplotlib.patches import Patch
import matplotlib.pyplot as plt

OUT=JMS/"results/chamber_wait_20261126"
CHARTS=OUT/"figures"
COLORS={"腔室加工":"#277E78","腔内等待":"#EBAB52","腔室旋转":"#675688","VTR取放":"#3E6485","周期间空腔":"#D8E0E6"}


def png(path):
    subprocess.run(["pdftoppm","-r","165","-singlefile","-png",str(path),str(path.with_suffix(""))],check=True)


def best(n):
    candidates=list(OUT.glob(f"*/n{n}/evidence.json"))+[OUT/f"n{n}/evidence.json"]
    def criteria(path):
        d=profile(cell.read(path.parent/"schedule.json"))
        chambers=list(d["chambers"].values())
        gap=[c["internal_empty"] for c in chambers]
        return (sum(c["occupied_wait"] for c in chambers),sum(gap),d["secondary"],d["cmax"],
                max(gap)-min(gap),d["equipment_release"],d["vtr_held_wait"])
    return min(candidates,key=criteria)


def main():
    CHARTS.mkdir(exist_ok=True)
    gantt.plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","SimHei","DejaVu Sans"],
                               "axes.unicode_minus":False,"pdf.fonttype":42})
    fig,axes=plt.subplots(2,1,figsize=(9.1,6.25))
    fig.subplots_adjust(left=.16,right=.975,top=.92,bottom=.16,hspace=.70)
    manifest={}
    for ax,n in zip(axes,(4,16)):
        endpoint=best(n)
        ev=cell.read(endpoint)
        path=endpoint.parent/"schedule.json"
        data=cell.read(path)
        initial=cell.read(CASES[n]/"schedule.json")
        assert sha(path)==ev["schedule_sha256"] and validate(data)["valid"]
        source=profile(initial)
        cand=profile(data)
        chart_info=dict(n=n,source=path.relative_to(JMS).as_posix(),source_sha256=sha(path),
            certificate=endpoint.relative_to(JMS).as_posix(),certificate_sha256=sha(endpoint),
            cmax=cand["cmax"],equipment_end=cand["equipment_release"],secondary=cand["secondary"])
        legend_labels=dict(gantt.LEGEND_LABELS)
        legend_labels.update({"腔室加工":"工艺加工","承片等待":"持片等待","ATR取片":"ATR取出",
                              "ATR放片":"ATR放入","VTR取放":"VTR取放"})
        with patch.object(gantt,"OUTPUT",CHARTS), patch.object(gantt,"LEGEND_LABELS",legend_labels):
            chart=gantt.draw(dict(summary=chart_info,replay=ev["physical_validation"],
                                  display={"intervals":len(build(data)[1])}))
        pdf=CHARTS/f"gantt_{n}_wafers.pdf"
        (CHARTS/chart["chart"]).replace(pdf)
        png(pdf)
        labels=[]
        for idx,(doc,stat,title) in enumerate(((initial,source,"原排程"),(data,cand,"候选排程"))):
            _,bars,_,_=build(doc)
            for k,c in enumerate((2,3)):
                y=idx*2+k
                labels.append(f"{title}   CH{c}")
                blocks=stat["chambers"][str(c)]
                lane=f"旋转腔 CH{c}"
                ax.broken_barh([(a,b-a) for a,b in blocks["empty_intervals"]],(y-.32,.64),
                               facecolor=COLORS["周期间空腔"],edgecolor="none")
                for b in bars:
                    if b["lane"]==lane:
                        ax.broken_barh([(b["start"],b["end"]-b["start"])],(y-.32,.64),
                                       facecolor=COLORS[b["action"]],edgecolor="none")
        wsum=lambda v:sum(c["occupied_wait"] for c in v["chambers"].values())
        gsum=lambda v:sum(c["internal_empty"] for c in v["chambers"].values())
        t=f"{n}片   ·   有片等待 {wsum(source):g} → {wsum(cand):g} s"
        if n==16:
            t+=f"   ·   周期间空腔 {gsum(source):g} → {gsum(cand):g} s"
        ax.set_title(t,loc="left",fontsize=12.5,pad=7)
        ax.set_xlim(0,source["equipment_release"]+4)
        ax.set_ylim(3.57,-.55)
        ax.set_yticks(range(4),labels,fontsize=9)
        ax.set_xlabel("时间 / s",fontsize=9)
        ax.axhline(1.5,linewidth=.6,color="#CCCCCC")
        ax.grid(axis="x",color="#DDE1E5",linewidth=.6);ax.set_axisbelow(True)
        ax.spines[["left","right","top"]].set_visible(False)
        ax.tick_params(axis="y",length=0)
        manifest[str(n)]={"evidence":str(endpoint.relative_to(JMS).as_posix()),"schedule":chart_info["source"],
                          "full_gantt":pdf.name,"original":source,"candidate":cand}
    names={"腔室加工":"工艺加工","腔内等待":"有片等待","腔室旋转":"旋转","VTR取放":"VTR取放","周期间空腔":"周期间空腔"}
    fig.legend(handles=[Patch(facecolor=color,label=names[action]) for action,color in COLORS.items()],
               loc="lower center",ncol=5,frameon=False,bbox_to_anchor=(.5,.018),fontsize=10)
    compare=CHARTS/"chamber_comparison.pdf"
    fig.savefig(compare,metadata={"CreationDate":None,"ModDate":None});plt.close(fig)
    png(compare)
    write(CHARTS/"manifest.json",manifest)


if __name__=="__main__":
    main()
