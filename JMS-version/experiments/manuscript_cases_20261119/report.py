"""Verify the saved solutions, write manuscript metrics, and draw just the two schedule figures."""
from collections import Counter
import csv
import gzip
from itertools import combinations
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cases import HERE, JMS, ROOT, dump, read, sha
from campaign import SWEEPS, complete
from worker import lane_metrics

sys.path.insert(0,str(HERE.parent/"finite_budget_20261116"))
from finite_budget import physical_metrics

TOL=2e-4


def same_numbers(values,other):
    return values.keys()==other.keys() and all(abs(v-other[k])<=TOL for k,v in values.items())


def checked(out,case,token):
    key=case["id"]
    if not complete(out,case,token):
        raise ValueError(f"Missing evidence for {key}")
    folder=out/"cases"/key
    e=read(folder/"evidence.json")
    cert=read(folder/"certificate.json")
    if (e["A_gap"],e["B_gap"],e["seed"],e["workers"],e["beam_width"],e["sweeps"])!=(1e-5,1e-5,1,1,14,SWEEPS):
        raise ValueError(f"Search parameters changed: {key}")
    window=read(folder/"windows.json")
    if (window["sweep"]!=len(SWEEPS) and not e["primary_analytical_target_met"]) or not window["beam_candidates"]:
        raise ValueError(f"Unfinished primary search: {key}")
    if any((r["relative_gap_limit"],r["seed"],r["workers"])!=(1e-5,1,1) for r in window["records"]):
        raise ValueError(f"Unexpected rolling-window settings: {key}")
    for label in ("primary","final"):
        data=read(folder/(label+".json"))
        proof=cert[label+"_certificate"]
        if (not proof["valid"] or not proof["replay"]["valid"] or not data["original_model_check"]
                or not data["validation"]["valid"] or proof["rows"]!=e["full_model_rows"]
                or data["config"]!=case["config"] or
                sum(bool(j["product"]) for j in data["jobs"])!=case["n"]):
            raise ValueError(f"Model or replay mismatch: {key}/{label}")
        if not same_numbers(e[label],physical_metrics(data)):
            raise ValueError(f"Cannot reproduce physical objectives: {key}/{label}")
        if lane_metrics(data)!=e[label+"_lanes"]:
            raise ValueError(f"Cannot reproduce equipment intervals: {key}/{label}")
    a,b=e["primary"],e["final"]
    if (b["cmax"]>a["cmax"]+TOL or b["secondary"]>a["secondary"]+TOL or
            abs(b["secondary"]-cert["primal"])>TOL or cert["dual"]>cert["primal"]+TOL or
            a["cmax"]+TOL<e["primary_lower_bound"]["seconds"]):
        raise ValueError(f"Invalid bounds or objective ordering: {key}")
    return e,cert


def archived_primary_certificate(case,makespan):
    if case["backend"]!="D": return None
    if case["id"]=="D_n2_4x1_sameLP":
        path=JMS/"revisions/20261103_results_default_residency/optimality_certificate.json"
        proof=read(path)
        if (not proof["original_objective_globally_optimal"] or proof["result_sha256"]!=case["source_sha256"]
                or proof["target_config"]!=case["config"] or abs(proof["old_lower_bound"]-makespan)>TOL):
            raise ValueError("Unmatched transferred optimality certificate")
        bound=proof["old_lower_bound"]
    else:
        path=ROOT/case["source"]
        data=read(path)
        if (path.name!="phase1.json" or data.get("status")!="optimal" or data.get("restricted_candidate_bounds") is not False
                or data.get("gap")!=0. or abs(data["dual_bound"]-makespan)>TOL):
            return None
        bound=data["dual_bound"]
    return dict(lower_bound_s=bound,source=path.relative_to(ROOT).as_posix(),sha256=sha(path))


def summarize(out):
    spec=read(out/"campaign.json")
    token=sha(out/"campaign.json")
    rows,entries=[],[]
    for case in sorted(spec["cases"],key=lambda c:(c["n"],c["backend"],c["id"])):
        e,cert=checked(out,case,token)
        key,cfg=case["id"],case["config"]
        b=e["final"]
        entry=dict(case=key,n=case["n"],backend=case["backend"],mix=case["mix"],figure=case["figure"],
                   source=case["source"],manuscript=case["manuscript"],evidence=f"cases/{key}/evidence.json",
                   evidence_sha256=sha(out/"cases"/key/"evidence.json"),primary=e["primary"],final=b,
                   unrestricted_A_lower=e["primary_lower_bound"]["seconds"],
                   A_analytical_target_met=e["primary_analytical_target_met"],conditional_B_status=cert["status"],
                   conditional_B_gap=cert["relative_gap"],conditional_B_target_met=cert["relative_gap"]<=1e-5,
                   rows=e["full_model_rows"],peak_rss_mib=e["resources"]["peak_rss_mib"])
        prior=archived_primary_certificate(case,b["cmax"])
        entry["archived_global_primary_certificate"]=prior
        entries.append(entry)
        row={"算例":key,"产品片数":case["n"],"4×1片数":case["mix"]["4x1"],"2×2片数":case["mix"]["2x2"],
             "模型版本":case["backend"],"清洁阈值H":cfg["cleaning_interval"],"辅助片库存":cfg["dummy_count"],
             "辅助片供源":cfg["source"],"腔室驻留限值_s":cfg["module_residency"],
             "机器人驻留限值_s":cfg["robot_residency"],"LP配置":json.dumps(cfg["load_ports"],separators=(",",":")),
             "种子":e["seed"],"A设置间隙_pct":.001,"B设置间隙_pct":.001}
        for label,name in (("initial","存档输入"),("primary","A"),("final","B")):
            values=e[label]
            for field,title in (("cmax","完工_s"),("wait_sum","总等待_s"),("wait_max","最大单项等待_s"),
                                ("rhythm","节拍偏差_s"),("rhythm_centers","有效节拍中心数"),("secondary","加权目标")):
                row[name+"_"+title]=round(values[field],6)
            if label=="initial": continue
            lane=e[label+"_lanes"]
            row[name+"_设备占用结束_s"]=round(lane["equipment_end"],6)
            row[name+"_双腔合计空闲_s"]=round(lane["idle"],6)
            for ch,metric in lane["chambers"].items():
                row[f"{name}_CH{ch}空闲_s"]=round(metric["idle"],6)
                row[f"{name}_CH{ch}最长空闲_s"]=round(metric["longest"],6)
        row.update({"A_工作负荷松弛下界_s":entry["unrestricted_A_lower"],
                    "A_相对该下界的差距_pct":round(100*e["primary_global_gap_upper"],8),
                    "A_按该下界达到间隙":entry["A_analytical_target_met"],
                    "另经原存档证实的全局最优完工_s":round(prior["lower_bound_s"],6) if prior else "",
                    "对应全局最优证据":prior["source"] if prior else "","B_固定结构下界":round(cert["dual"],6),
                    "B_固定结构上界":round(cert["primal"],6),"B_固定结构间隙_pct":round(100*cert["relative_gap"],8),
                    "B_固定结构求解状态":cert["status"],"分组候选数":e["group_candidates"],
                    "滚动窗口数":e["window_count"],"A排程来源":e["selected_origin"],"完整模型约束数":entry["rows"],
                    "原模型逐行校验":True,"最终重放检查数":e["replay_checks"],"工作进程峰值_MiB":entry["peak_rss_mib"],
                    "本次工作进程耗时_s":round(e["worker_wall_s"],3),"对应文稿图表":" / ".join(case["manuscript"]),
                    "甘特图":case["figure"] or "","排程与校验目录":f"cases/{key}"})
        rows.append(row)
    path=out/"results_summary.csv"
    tmp=path.with_suffix(".csv.tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)
    document=dict(protocol=token,solved=len(entries),by_wafer_count=dict(Counter(x["n"] for x in entries)),
                  expected_gantt=[x["case"] for x in entries if x["figure"]],
                  primary_reached_workload_bound=sum(x["A_analytical_target_met"] for x in entries),
                  confirmed_against_archived_global_primary_bound=sum(bool(x["archived_global_primary_certificate"]) for x in entries),
                  secondary_reached_conditional_target=sum(x["conditional_B_target_met"] for x in entries),
                  secondary_status_counts=dict(Counter(x["conditional_B_status"] for x in entries)),
                  peak_single_worker_rss_mib=max(x["peak_rss_mib"] for x in entries),
                  primary_scope="grouping beam and four rolling-window sweeps; workload relaxation lower bound",
                  secondary_scope="optimized event times and eligible intra-pair synchronization with phase-A discrete choices fixed",
                  secondary_objective="wait_sum + 10*wait_max + 25*rhythm",seed=1,
                  historical_screening=dict(screened=len(spec["historical_qualification"]),measured=6),
                  csv_sha256=sha(path),cases=entries)
    dump(out/"report.json",document)
    print(f"Verified {len(rows)} pairs of schedules; summary: {path}",flush=True)
    return document


def display_schedule(source):
    data=read(source)
    assignment=source.parent/"final_assignment.json.gz"
    with gzip.open(assignment,"rt",encoding="utf8") as f:
        active={k for k,v in json.load(f)["nonzero"].items() if k.startswith("sync_") and v>.5}
    largest=0.
    found=set()
    for a,b in combinations(data["events"],2):
        keys=active.intersection((f"sync_{a['name']}_{b['name']}",f"sync_{b['name']}_{a['name']}"))
        if not keys: continue
        residual=max(abs(a[t]-b[t]) for t in ("start","end"))
        if (a["robot"],a["location"],a["kind"])!=(b["robot"],b["location"],b["kind"]) or residual>TOL:
            raise ValueError("Inconsistent synchronized handling in figure source")
        largest=max(largest,residual)
        found.update(keys)
        # The paper's renderer groups synchronous events by exact float keys.
        # Use their model-certified common time for drawing the one robot action.
        b["start"],b["end"]=a["start"],a["end"]
    if found!=active: raise ValueError("Missing synchronized handling in figure source")
    return data,dict(assignment_sha256=sha(assignment),synchronous_pairs=len(active),
                     max_synchronous_display_adjustment_s=largest)


def figures(out):
    sys.path.insert(0,str(JMS/"tools"))
    import render_journal_schedule_examples as render
    doc=summarize(out)
    dest=out/"figures"
    dest.mkdir(exist_ok=True)
    render.plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","SimHei","DejaVu Sans"],
                                 "font.size":13,"axes.unicode_minus":False,"pdf.fonttype":42,"svg.fonttype":"path"})
    manifest=[]
    with TemporaryDirectory(dir=dest) as tmp:
        stage=Path(tmp)
        with patch.object(render,"OUT",stage):
            for case in (c for c in doc["cases"] if c["figure"]):
                source=out/"cases"/case["case"]/"final.json"
                data,sync=display_schedule(source)
                lanes,bars,paths,_=render.build(data)
                if len(paths)!=len(data["jobs"]): raise ValueError("Incomplete drawn wafer paths")
                info=render.draw(data,dict(lanes=lanes,bars=bars,explicit_events_covered=len(data["events"]),
                                           overlapping_display_states=0),case["figure"],single_column=True)
                if abs(info["cmax"]-case["final"]["cmax"])>TOL: raise ValueError("Figure makespan mismatch")
                manifest.append(dict(case=case["case"],source=source.relative_to(out).as_posix(),source_sha256=sha(source),**sync,
                                     **info,artifacts={p.name:sha(p) for p in sorted(stage.glob(case["figure"]+".*"))}))
        if len(manifest)!=2 or len(list(stage.iterdir()))!=6: raise ValueError("Unexpected manuscript figure set")
        for p in stage.iterdir(): p.replace(dest/p.name)
    dump(dest/"manifest.json",dict(protocol=doc["protocol"],figures=manifest))
    verify_figures(out)


def verify_figures(out):
    doc=read(out/"report.json")
    dest=out/"figures"
    manifest=read(dest/"manifest.json")
    if manifest["protocol"]!=doc["protocol"] or [e["case"] for e in manifest["figures"]]!=doc["expected_gantt"]:
        raise ValueError("Wrong manuscript figure selection")
    for entry in manifest["figures"]:
        source=out/entry["source"]
        if (sha(source)!=entry["source_sha256"] or sha(source.parent/"final_assignment.json.gz")!=entry["assignment_sha256"]):
            raise ValueError("Changed figure schedule or synchronization witness")
        if {Path(n).suffix for n in entry["artifacts"]}!={".pdf",".svg",".png"}: raise ValueError("Missing figure format")
        for name,digest in entry["artifacts"].items():
            if sha(dest/name)!=digest: raise ValueError(f"Changed figure {name}")
    print(f"Verified both manuscript schedule figures at {dest}",flush=True)
