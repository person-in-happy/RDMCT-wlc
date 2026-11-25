"""Independently reconstruct the three objectives from native schedules and verify the Chinese tables."""
import argparse
import csv
import importlib.util
from supplement import HERE, OUT, ROOT, checked, digest, load, save

spec = importlib.util.spec_from_file_location("native_manuscript_audit",
        HERE.parent / "quota_objective_20261125/verify_manuscript.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
audit.OUT = OUT.parent
audit.MANUSCRIPT = audit.JMS / "JMS_Review_CN.tex"
native_score = audit.independent


def independent(schedule, closed=True):
    physical = native_score(schedule, closed=True)
    d = physical["residence_range"]
    loss = d**2 / 2 if d <= 1 else d - .5
    physical.update(huber_penalty=loss, secondary=physical["mean_residence"]+loss+physical["clean_deficit"])
    return physical


def publish():
    manifest = load(OUT/"manifest.json")
    groups = {"threshold":[], "structure":[]}
    for name, job in manifest.items():
        src = OUT / job["key"]
        if not checked(src, job):
            raise ValueError(name)
        result = load(src/"result.json")
        actual = independent(load(src/"schedule.json"))
        audit.check_fields(actual, result["measured"], {k:k for k in actual if k in result["measured"]})
        initial = independent(load(HERE.parents[2]/job["source"]/job["schedule"]))
        audit.check_fields(initial, result["initial"], {k:k for k in initial if k in result["initial"]})
        row = dict(name=name, seed=result["seed"], f_A=actual["cmax"], f_B=actual["secondary"],
                   initial_f_B=initial["secondary"], mean=actual["mean_residence"], spread=actual["residence_range"],
                   penalty=actual["huber_penalty"], clean_deficit=actual["clean_deficit"],
                   status=result["record"]["status"], source=job["key"])
        if name.startswith("grid_"):
            case, ga, gb = name[5:].split("__")
            groups["threshold"].append(dict(case=case, gA=ga, gB=gb, **row))
        else:
            groups["structure"].append(row)
    for key, rows in groups.items():
        with (OUT/f"{key}_cells.csv").open("w", encoding="utf8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def verify_front_and_figures():
    results = OUT.parent
    cert = results / "frontier/certificate.json"
    curve = load(cert)
    assert curve["H3_complete_frontier"] and curve["H10_attainment"]["lower"] == curve["H10_attainment"]["upper"] == 576.625
    figures = load(results / "reuse/figure_evidence.json")
    assert figures["figure_sha256"] == digest(ROOT/figures["figure"])
    assert figures["global_proof_sha256"] == digest(cert)
    assert figures["far_witness_sha256"] == digest(ROOT/figures["far_witness"])
    assert load(results/"frontier/preference_sensitivity.json")["certificate_sha256"] == digest(cert)
    eps = audit.csv_rows(results/"reuse/epsilon_summary.csv")
    assert len(eps) == 20 and sum(r["structure"]=="short" for r in eps) == 12
    for r in eps:
        p = ROOT / r["record"]
        assert digest(p) == r["sha256"]
        if r["status"] == "infeasible":
            assert r["structure"] == "long"
            continue
        physical = independent(load(p.parent/"schedule.json"))
        audit.check_fields(physical,r,dict(cmax="C",mean_residence="mean",residence_range="D",clean_deficit="E",secondary="F"))
        if r["structure"]=="short":
            t = min(.75,float(r["cap"])-553)
            assert abs(physical["secondary"]-(3.75-.75*t+.5*t*t)) < 2e-6
    local = audit.csv_rows(results/"reuse/epsilon_local.csv")
    final_window = [r for r in local if r["batch"]=="epsilon_576"]
    assert len(local)==8 and {float(r["cap"]) for r in final_window}=={576,576.25,576.5,576.625}
    for r in local:
        p = ROOT/r["witness"]
        assert digest(p)==r["witness_sha256"] and digest(p.parent/"schedule.json")==r["schedule_sha256"]
        physical = independent(load(p.parent/"schedule.json"))
        audit.check_fields(physical,r,dict(cmax="C",mean_residence="mean",residence_range="D",clean_deficit="E",secondary="F"))
    scales = load(results/"reuse/pool/scale_figures.json")
    for data in scales.values():
        item = data["repr"]
        assert data["matches_both_pool_minima"]
        schedule = ROOT/item["source"]
        assert digest(schedule) == item["source_sha256"]
        physical = independent(load(schedule))
        audit.check_fields(physical,item,dict(cmax="C",secondary="F",clean_deficit="E",residence_range="D"))
    return dict(curve_and_attainment_sha256=digest(cert),figure_sha256=figures["figure_sha256"],
                initial_epsilon_cells=len(eps),additional_epsilon_cells=len(local),
                final_endpoint_epsilon_cells=len(final_window),scale_figures=len(scales))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish-only", action="store_true")
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    publish()
    if not args.publish_only:
        audit.independent = independent
        audit.main(args.partial, True)
        if not args.partial:
            summary = OUT.parent/"manuscript_validation.json"
            save(summary,load(summary)|verify_front_and_figures())
