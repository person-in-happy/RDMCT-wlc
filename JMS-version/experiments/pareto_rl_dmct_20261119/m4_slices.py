"""Continuous Pareto boundaries of the integer schedules returned in nominal M4."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

from common import JMS, TOL, config, digest, save
from evaluate import read, write_csv
from native import Native
from witness import sparse_witness
import numpy as np

sys.path.append(str(JMS/"experiments/pareto_front_20261118"))
from slices import Projected


def dominated_on_slices(a,b,groups):
    for g in groups:
        candidates=list(g["vertices"])
        for left,right in zip(g["vertices"],g["vertices"][1:]):
            if left[0]<=a<=right[0] and right[0]-left[0]>TOL:
                ratio=(a-left[0])/(right[0]-left[0])
                candidates.append((a,left[1]+ratio*(right[1]-left[1])))
        if any(x<=a+TOL and y<=b+TOL and (x<a-TOL or y<b-TOL) for x,y in candidates):
            return True
    return False


def envelope(groups):
    """Efficient pieces for the union of the projected polytopes, in two objectives."""
    raw=[]
    xs=[]
    vertices=[]
    for group in groups:
        points=group["vertices"]
        vertices.extend(tuple(p) for p in points)
        xs.extend(p[0] for p in points)
        for left,right in zip(points,points[1:]):
            if right[0]-left[0]>TOL and left[1]-right[1]>TOL:
                slope=(right[1]-left[1])/(right[0]-left[0])
                raw.append((left[0],right[0],slope,left[1]-slope*left[0],group["integer_sha256"]))
    flat=[(x,max(xs),0.,y,None) for x,y in vertices]
    lines=raw+flat
    for i,(lo,hi,k,b,_) in enumerate(lines):
        for li,ri,j,d,_ in lines[:i]:
            if abs(k-j)>1e-9:
                cross=(d-b)/(k-j)
                if max(lo,li)+TOL<cross<min(hi,ri)-TOL:
                    xs.append(cross)
    knots=sorted(set(round(x,7) for x in xs))
    parts=[]
    for l,r in zip(knots,knots[1:]):
        if r-l<TOL:
            continue
        mid=(l+r)/2
        feasible=[v for v in lines if v[0]-TOL<=mid<=v[1]+TOL]
        if not feasible:
            continue
        _,_,k,b,origin=min(feasible,key=lambda v:v[2]*mid+v[3])
        if k>=-1e-9:
            continue
        segment=dict(A_left=l,B_left=k*l+b,A_right=r,B_right=k*r+b,integer_sha256=origin)
        if parts and parts[-1]["integer_sha256"]==origin and abs(parts[-1]["A_right"]-l)<=TOL:
            last=parts[-1]
            old_slope=(last["B_right"]-last["B_left"])/(last["A_right"]-last["A_left"])
            if abs(old_slope-k)<1e-7:
                last.update(A_right=r,B_right=k*r+b)
                continue
        parts.append(segment)
    candidates=[]
    for x,y in sorted(set((round(a,7),round(b,7)) for a,b in vertices)):
        best=min((k*x+b for lo,hi,k,b,_ in lines if lo-TOL<=x<=hi+TOL),default=y)
        earlier=min((b for a,b in vertices if a<x-TOL),default=float("inf"))
        if y<=best+TOL and y<earlier-TOL:
            candidates.append((x,y))
    for part in parts:
        part["left_included"]=not dominated_on_slices(part["A_left"],part["B_left"],groups)
        part["right_included"]=not dominated_on_slices(part["A_right"],part["B_right"],groups)
    return parts,candidates


def project(campaign):
    target=campaign/"evaluation"/"m4_slices"
    target.mkdir(parents=True,exist_ok=True)
    state=read(campaign/("completed_for_audit.json" if (campaign/"completed_for_audit.json").exists() else "finished.json"))
    inputs=[]
    for ident,rel in state["done"].items():
        runpath=campaign/rel
        run=read(runpath)
        if run["spec"]["suite"]=="main" and run["spec"]["case"]=="M4":
            inputs.extend((ident,runpath.parent/entry["schedule"]) for entry in run["front"])
    if not inputs:
        raise ValueError("No completed M4 main runs")
    start=time.monotonic()
    cfg=config("M4")
    full=Native(cfg,1,25)
    groups=[]
    by_hash={}
    try:
        pg=Projected(full.x)
        for i,(ident,path) in enumerate(inputs):
            with gzip.open(path,"rt",encoding="utf-8") as f:
                data=json.load(f)
            vals=sparse_witness(cfg,data)
            discrete=np.array([round(vals.get(pg.names[j],0)) for j in pg.id],dtype=np.int32)
            code=hashlib.sha256(discrete.astype("<i4",copy=False).tobytes()).hexdigest()
            if code in by_hash:
                by_hash[code]["sources"].append([ident,path.name])
                continue
            pg.setup(discrete)
            vectors=pg.front()
            vertices=[pg.verify(v).tolist() for v in vectors]
            mids=[]
            for j,(first,last) in enumerate(zip(vectors,vectors[1:])):
                midpoint=pg.verify((first+last)/2)
                if np.max(np.abs(midpoint-(np.asarray(vertices[j])+vertices[j+1])/2))>TOL:
                    raise ValueError("Physical midpoint differs from its linear projection")
                mids.append(midpoint.tolist())
            artifact=target/f"fixed_{len(groups)+1:03d}.npz"
            np.savez_compressed(artifact,discrete=discrete,vertices=np.array(vectors))
            rec=dict(integer_sha256=code,sources=[[ident,path.name]],vertices=vertices,midpoints=mids,
                     vector_file=artifact.name,vector_file_sha256=digest(artifact))
            by_hash[code]=rec
            groups.append(rec)
            if i%10==0:
                elapsed=time.monotonic()-start
                print(f"四片结构投影 {i+1}/{len(inputs)} | 失败 0 | 独立结构 {len(groups)} | "
                      f"预计剩余 {elapsed*(len(inputs)-i-1)/(i+1):.0f}s",flush=True)
        pieces,points=envelope(groups)
        earlier=JMS/"results/pareto_front_20261118_r1/n4"
        chain=read(earlier/"chain_slice_replay/results.json")[0]
        previous=[[(v["metrics"]["cmax"],v["metrics"]["secondary"]) for v in chain["vertices"]],
                  read(earlier/"verified_segments/segments.json")[0]["vertices"]]
        prior_dominated=[]
        for seq in previous:
            for a,b in seq:
                prior_dominated.append(dict(A=a,B=b,dominated_by_current_slice=dominated_on_slices(a,b,groups)))
        save(target/"projection.json",dict(input_schedules=len(inputs),structures=len(groups),
             vertices=sum(len(g["vertices"]) for g in groups),segments=sum(len(g["midpoints"]) for g in groups),
             envelope_segments=pieces,envelope_vertices=points,original_rows=full.x.original_dimensions["constraints"],
             historical_fixed_structure_segments=previous,historical_endpoints=prior_dominated,
             tested_endpoint_and_midpoint=True,lp_solves=pg.lps,elapsed_s=time.monotonic()-start,slices=groups))
    finally:
        full.close()
    write_csv(target/"envelope_segments.csv",pieces)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({"font.family":["Microsoft YaHei","DejaVu Sans"],"axes.spines.top":False,
                         "axes.spines.right":False,"axes.unicode_minus":False,"savefig.dpi":190})
    fig,axes=plt.subplots(1,2,figsize=(10.5,4.5),layout="constrained")
    for ax in axes:
        for curve in previous:
            ax.plot(*zip(*curve),linestyle="--",color="#ac661f",linewidth=1.2,marker="x",markersize=4)
        for g in groups:
            ax.plot(*zip(*g["vertices"]),marker=".",markersize=4,linewidth=.8,color="#acb4bb",alpha=.6)
        for p in pieces:
            ax.plot([p["A_left"],p["A_right"]],[p["B_left"],p["B_right"]],color="#00786c",linewidth=2)
            for side in ("left","right"):
                if not p[side+"_included"]:
                    ax.scatter(p["A_"+side],p["B_"+side],s=28,facecolors="white",edgecolors="#00786c",zorder=4)
        if points:
            ax.scatter(*zip(*points),s=22,color="#00786c",zorder=3)
        ax.grid(alpha=.16)
        ax.set(xlabel="产品完工时间 A（秒）",ylabel="等待与节拍指标 B（加权秒）")
    axes[0].set_title("已访问结构的可行边界",loc="left")
    axes[1].set_title("低等待区间",loc="left")
    low=min(y for x,y in points)
    relevant=[x for x,y in points if y<=low+100]
    if relevant:
        left,right=min(relevant),max(relevant)
        axes[1].set(xlim=(left-6,right+6),ylim=(low-7,low+100))
    fig.legend(handles=[Line2D([0],[0],color="#acb4bb",label="单一整数结构的边界",marker="."),
                        Line2D([0],[0],color="#00786c",label="本次结构合并后的有效部分",marker="o",markersize=4),
                        Line2D([0],[0],color="#ac661f",label="先前已验证的三个结构内线段",ls="--",marker="x"),
                        Line2D([0],[0],color="#00786c",label="被其他结构支配的端点",ls="none",marker="o",mfc="white")],
               loc="outside lower center",ncol=2,frameon=False)
    fig.savefig(target/"m4_conditional_front_CN.png")
    plt.close(fig)
    print(f"四片投影完成 | {len(groups)} 个整数结构 | {len(pieces)} 个经验边界线段",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign",type=Path)
    project(parser.parse_args().campaign.resolve())
