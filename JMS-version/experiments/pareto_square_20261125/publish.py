"""Audit the nondominated archive and export the certified curves without interpolation between samples."""
import csv
import os
import sys
from pathlib import Path
import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from support import HERE,JMS,R,OUT,OLD,read,write,digest
sys.path.insert(0,str(HERE.parent/"square_residence_20261125"))
from score import metrics
from solver import cell
sys.path.insert(0,str(cell.BACKENDS["D"]))
from validate import validate

FIG=JMS/"figures/rolling_refinement_20261119/fig_pareto_scales_square_cn.pdf"
BLUE="#20598a"
ORANGE="#ad531d"


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def save_csv(path,rows):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def observations():
    files={}
    for row in csv_rows(OLD/"all_observations.csv"):
        files[JMS/row["schedule"]]=(row["sha256"],"archived",int(row["rows"]))
    config=read(R/"table3_mixed16_20261125/input.json")["config"]
    for group in ("fixed/*/*","native/*/*"):
        for p in OUT.glob(group+"/result.json"):
            r=read(p)
            if not r.get("files") or "16" not in p.parts[-3] and group.startswith("fixed"):continue
            files[p.parent/"schedule.json"]=(r["files"]["schedule.json"],"time_cap" if group.startswith("fixed") else "new_structure",r["original_rows"])
    for p in (R/"square_table4_20261125/runs").glob("n16_H10*/result.json"):
        rec=read(p)
        if rec.get("files"):files[p.parent/"schedule.json"]=(rec["files"]["schedule.json"],"method_comparison",rec["original_rows"])
    for row in csv_rows(R/"square_grid_20261125/threshold_cells.csv"):
        if row["case"]=="D_n16_H10_mixed_dual":
            f=JMS/row["schedule_path"]
            r=read(f.parent/"result.json") if (f.parent/"result.json").exists() else read(f.parent/"primary.json")
            files[f]=(row["schedule_sha256"],"tolerance_grid",r.get("original_rows",r.get("rows",0)))
    obs=[]
    for p,(sig,origin,rows) in sorted(files.items()):
        assert digest(p)==sig and rows>0
        d=read(p);assert d["config"]==config,p
        q=validate(d);assert q["valid"] and q["checks"]>0
        z=metrics(d)
        assert abs(z["cmax"]-q["product_return_cmax"])<1e-5
        assert abs(z["secondary"]-(z["mean_residence"]+.5*z["residence_range"]**2+z["clean_deficit"]))<1e-8
        obs.append(dict(schedule=str(p.relative_to(JMS)).replace(chr(92),"/"),sha256=sig,origin=origin,rows=rows,checks=q["checks"],**z))
    # Collapse numerical ties at the original feasibility tolerance; keep a checked schedule for every coordinate.
    coordinates={}
    for p in obs:
        key=(round(p["cmax"],4),round(p["secondary"],4))
        if key not in coordinates or (p["cmax"],p["secondary"])<(coordinates[key]["cmax"],coordinates[key]["secondary"]):coordinates[key]=p
    frontier=[];best=float("inf")
    for (c,b),r in sorted(coordinates.items()):
        if b<best:
            exact=810<=c<=811
            if exact:
                t=r["cmax"]-810;assert abs(r["secondary"]-(7.625-.125*t+.5*(30-t)**2))<3e-5
            frontier.append(dict(r,scope="certified_continuous_curve" if exact else "nondominated_in_evaluated_archive"))
            best=b
    return obs,frontier,coordinates


def graphics(cert,front):
    os.environ["SOURCE_DATE_EPOCH"]="0"
    mpl.rcParams.update({"font.sans-serif":["Microsoft YaHei","DejaVu Sans"],"axes.unicode_minus":False,
        "font.size":8,"axes.linewidth":.7,"pdf.fonttype":42,"mathtext.fontset":"stix","xtick.labelsize":7.5,"ytick.labelsize":7.5})
    fig=plt.figure(figsize=(7.16,4.36))
    outer=fig.add_gridspec(2,1,height_ratios=(1,1.12),left=.088,right=.978,top=.90,bottom=.12,hspace=.72)
    top=outer[0].subgridspec(1,3,width_ratios=(.84,1.08,1.05),wspace=.49)
    a=fig.add_subplot(top[0]);b=fig.add_subplot(top[1]);c=fig.add_subplot(top[2])
    below=outer[1].subgridspec(1,3,width_ratios=(1.52,.95,.82),wspace=.41)
    d=fig.add_subplot(below[0]);e=fig.add_subplot(below[1]);f=fig.add_subplot(below[2])
    for ax in (a,b,c,d,e,f):
        ax.spines[["right","top"]].set_visible(False)
        ax.tick_params(length=2.6,width=.65,pad=2)
        ax.grid(axis="y",color="#e7ebef",linewidth=.5)
    def title(left,right,text):
        l,r=left.get_position(),right.get_position()
        fig.text((l.x0+r.x1)/2,l.y1+.035,text,ha="center",va="bottom",fontsize=9.3)
    def xlabel(left,right):
        l,r=left.get_position(),right.get_position()
        fig.text((l.x0+r.x1)/2,l.y0-.065,r"工期 $f_A$（s）",ha="center",va="center",fontsize=8)
    a.set_ylabel(r"工艺目标 $f_B$（等效 s）",labelpad=4)
    d.set_ylabel(r"工艺目标 $f_B$（等效 s）",labelpad=4)
    a.plot([397,417],[3.5,3.46875],"o",ms=4.3,color=BLUE)
    a.set(xlim=(394,420),xticks=(397,417),ylim=(3.462,3.507),yticks=(3.47,3.48,3.49,3.50))
    title(a,a,r"(a)  4 片，$H=3,10$");xlabel(a,a)
    t=np.linspace(0,.75,170);b.plot(553+t,3.75-.75*t+.5*t*t,color=BLUE,lw=1.45)
    b.plot([553,553.75],[3.75,3.46875],"o",ms=3.3,color=BLUE)
    b.set(xlim=(552.965,553.79),xticks=(553,553.375,553.75),xticklabels=("553","553.375","553.75"),
          ylim=(3.445,3.778),yticks=(3.47,3.60,3.75))
    b.text(.98,.91,r"$H=3,10$",transform=b.transAxes,color=BLUE,ha="right",fontsize=7.5)
    start,end=cert["eight"]["tail_interval"];u=np.linspace(start-576,end-576,170)
    c.plot(576+u,3.625-.625*u+.5*u*u,color=ORANGE,lw=1.45)
    c.plot(start,3.46875,"o",ms=4.2,mfc="white",mec=ORANGE,mew=1)
    c.plot(end,3.4296875,"o",ms=3.4,color=ORANGE)
    c.set(xlim=(576.328,576.642),xticks=(576.35,576.5,576.625),xticklabels=("576.35","576.5","576.625"),
          ylim=(3.425,3.474),yticks=(3.43,3.45,3.47))
    c.text(.96,.91,r"$H=10$",transform=c.transAxes,color=ORANGE,ha="right",fontsize=7.5)
    title(b,c,"(b)  8 片");xlabel(b,c)
    partition=(lambda x:x<950,lambda x:950<=x<1090,lambda x:x>=1090)
    axes=(d,e,f);groups=[[point for point in front if condition(point["cmax"])] for condition in partition]
    assert sum(map(len,groups))==len(front) and all(groups)
    for ax,points in zip(axes,groups):
        for row in points:
            x=row["cmax"];y=row["secondary"];exact=row["scope"]=="certified_continuous_curve"
            ax.plot(x,y,marker="o",ms=3.6 if not exact else 3.1,mew=.85,mfc=BLUE if exact else "white",mec=BLUE,ls="none")
    t=np.linspace(0,1,160);d.plot(810+t,7.625-.125*t+.5*(30-t)**2,c=BLUE,lw=1.55,zorder=1)
    d.set(xlim=(min(p["cmax"] for p in groups[0])-.8,max(p["cmax"] for p in groups[0])+1.6),
          ylim=(55,477),yticks=(80,200,320,450),xticks=(810,812,815,819,823))
    xx=[p["cmax"] for p in groups[1]]
    e.set(xlim=(min(xx)-.6,max(xx)+.7),ylim=(3,22),yticks=(5,10,15,20))
    if max(xx)-min(xx)<=5:e.set_xticks(sorted(set(round(z,2) for z in xx)))
    xx=[p["cmax"] for p in groups[2]]
    f.set(xlim=(min(xx)-18,max(xx)+18),ylim=(3.396,3.437),yticks=(3.40,3.415,3.43))
    f.set_xticks([min(xx),max(xx)],labels=[f"{n:.3f}".rstrip("0").rstrip(".") for n in (min(xx),max(xx))])
    for ax,points in zip(axes,groups):
        x0,x1=ax.get_xlim();y0,y1=ax.get_ylim()
        assert all(x0<=p["cmax"]<=x1 and y0<=p["secondary"]<=y1 for p in points),(points,(x0,x1,y0,y1))
    title(d,f,r"(c)  16 片，$H=10$");xlabel(d,f)
    fig.savefig(FIG,metadata={"Title":"混合工艺的完工时间与二次驻留目标前沿","CreationDate":None,"ModDate":None})
    import pymupdf
    with pymupdf.open(FIG) as document:
        document[0].get_pixmap(matrix=pymupdf.Matrix(2.1,2.1),alpha=False).save(OUT/"figure_preview.png")
    plt.close(fig)


def main():
    cert=read(OUT/"certificate.json");obs,front,coords=observations()
    save_csv(OUT/"all_observations.csv",obs);save_csv(OUT/"sixteen_pareto.csv",front)
    graphics(cert,front)
    grid=[]
    for f in OUT.glob("fixed/*/cap_*/result.json"):
        r=read(f);grid.append(dict(scale=8 if f.parts[-3]=="long8" else 16,kind="time_cap",case=f.parts[-3],cap=r["cap"],spread_cap_s="",status=r["status"]))
    for f in OUT.glob("search/*/result.json"):
        r=read(f);grid.append(dict(scale=16,kind="spread_limit_minimize_C" if "spread_limit" in r else "time_cap",
                      case=f.parts[-2],cap=r["cap"],spread_cap_s=r.get("spread_limit",""),status=r["status"]))
    save_csv(OUT/"search_design.csv",grid)
    prior16={read(f)["cap"] for f in OLD.glob("sixteen*/cap_*/result.json")}
    new16={r["cap"] for r in grid if r["scale"]==16 and r["kind"]=="time_cap"}
    new8={r["cap"] for r in grid if r["scale"]==8}
    bounds=cert["sixteen"]["cap812_squared_lower_by_pattern"]
    u=metrics(read(OUT/"native/p26_814/p_812_129_15/schedule.json"))["secondary"]
    assert abs(min(p["secondary"] for p in front if abs(p["cmax"]-812)<1e-6)-u)<1e-5
    epts=[p for p in front if p["scope"]=="certified_continuous_curve"]
    res=dict(objective=cert["score"],delta=1,gamma=1,sample_records=len(obs),unique_schedules=len({p["sha256"] for p in obs}),
        distinct_objective_vectors=len(coords),nondominated_schedule_coordinates=len(front),independently_solved_points_on_certified_16_curve=len(epts),
        archive_only_coordinates=len(front)-len(epts),fixed_original_structure_epsilon_runs=len(list(OUT.glob("fixed/*/cap_*/result.json"))),
        total_time_cap_runs=sum(r["kind"]=="time_cap" for r in grid),spread_constrained_runs=sum(r["kind"]=="spread_limit_minimize_C" for r in grid),
        eight_C_caps=sorted(new8),sixteen_pure_C_caps=sorted(new16),sixteen_caps_additional_to_prior_16_sweep=sorted(new16-prior16),
        sixteen_D_levels=sorted({r["spread_cap_s"] for r in grid if r["kind"]=="spread_limit_minimize_C"}),sixteen_qualified_ranges=cert["sixteen"]["interval"],
        eight_qualified_ranges=[cert["eight"]["short_interval"],cert["eight"]["tail_interval"]],four_global_points=[[397,3.5],[417,3.46875]],
        real_bound_at812=[min(bounds.values()),u],left_to_812_drop_at_least=bounds["20"]-u,
        figure=str(FIG.relative_to(JMS)).replace(chr(92),"/"),figure_sha256=digest(FIG),proof_sha256=digest(OUT/"certificate.json"),
        archive_sha256=digest(OUT/"all_observations.csv"),observed_frontier_sha256=digest(OUT/"sixteen_pareto.csv"),grid_sha256=digest(OUT/"search_design.csv"))
    write(OUT/"validation.json",res);print({k:res[k] for k in ("sample_records","nondominated_schedule_coordinates","archive_only_coordinates","real_bound_at812","figure_sha256")},flush=True)


if __name__=="__main__":main()
