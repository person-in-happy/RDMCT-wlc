"""Measured scheduling instances and frozen inputs in the Chinese review manuscript."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
ROOT = JMS.parent
RESULTS = JMS / "results"
SMALL = RESULTS / "current_defaults_small_prepared_20261103" / "runs"
PAPER = RESULTS / "current_defaults_paper_20261104_075634" / "runs"
REFINEMENT = RESULTS / "pjob_nondecreasing_paper_all_20261102_231102" / "references"
RESTRICTED = RESULTS / "pjob_nondecreasing_qualification_all_20261103_032308" / "references"
SCREEN = RESULTS / "journal_d_qualification_20261109_r1"
BACKENDS = {"D": JMS / "model4_pjob_nonprocessing_20261103",
            "E": JMS / "model4_pjob_nondecreasing_20261102"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def catalog():
    observed, screen = [], []

    def include(key, family, folder, schedule, assignment, references, figure=None):
        src, values = folder / schedule, folder / assignment
        data = read(src)
        cfg = data["config"]
        counts = {m:sum(port[m] for port in cfg["load_ports"].values()) for m in ("4x1", "2x2")}
        if not data["jobs"] or sum(counts.values()) != sum(bool(j["product"]) for j in data["jobs"]):
            raise ValueError(f"Incomplete archived schedule in {src}")
        observed.append(dict(id=key, backend=family, config=cfg, mix=counts, n=sum(counts.values()),
                             source=src.relative_to(ROOT).as_posix(), source_sha256=sha(src),
                             assignment=values.relative_to(ROOT).as_posix(), assignment_sha256=sha(values),
                             manuscript=references, figure=figure))

    for n, key, manifest, field in (
        (2, "D_n2_4x1_sameLP", "current_defaults_20261103", "result"),
        (16, "D_n16_4x1", "current_d_n16_20261111", "source"),
    ):
        m = read(JMS / "figures" / manifest / "manifest.json")
        source = Path(m[field])
        if sha(source) != m[field + "_sha256"]:
            raise ValueError(f"Changed source for the {n}-wafer manuscript figure")
        tables = ["tab:journal-structure-cn", "tab:journal-algorithm-cn"] if n == 2 else ["tab:joint-two-stage-cn"]
        include(key, "D", source.parent, source.name, "variables.json",
                [("fig:small-optimal-gantt-cn" if n == 2 else "fig:current-defaults-gantt-cn"), *tables],
                figure=f"fig_schedule_n{n}_cn")
    for key, case in (("D_n2_4x1_crossLP", "n2_H3_4x1_dual"), ("D_n2_mixed", "n2_H3_mixed_dual")):
        include(key, "D", SMALL / (case + "__s1__scip"), "phase1.json", "variables_phase1.json",
                ["tab:journal-structure-cn", "tab:journal-algorithm-cn"])
    include("D_n4_mixed_H10", "D", PAPER / "n4_H10_mixed_dual__s1__scip",
            "phase1.json", "variables_phase1.json",
            ["tab:joint-two-stage-cn", "tab:journal-structure-cn", "tab:journal-algorithm-cn"])
    for n in (4, 8):
        for h in (3, 10):
            for source in ("single", "dual"):
                case = f"n{n}_H{h}_mixed_{source}"
                refs = ["tab:refinement-ablation-cn"]
                if source == "dual":
                    refs.append("tab:structure-ablation-cn")
                include("E_" + case, "E", REFINEMENT / case, "reference.json", "common.json", refs)
    for source in ("single", "dual"):
        include(f"E_n8_H3_mixed_{source}_restricted", "E", RESTRICTED / f"qualification_n8_mixed_{source}",
                "reference.json", "common.json", ["tab:refinement-ablation-cn"])
    include("E_n16_2x2", "E",
            RESULTS / "pjob_fifo_crossover_all_20261030_190540/runs/n16_H10_2x2_dual__s1__joint",
            "result.json", "variables_phase1.json", ["tab:joint-two-stage-cn", "tab:rhythm-weight-cn"])
    # The paper imported a FIFO-era assignment into its later E formulation.
    # Compare emitted rows to that E run, while keeping the original warm start.
    reference = RESULTS / "finite_budget_20261116_r1/runs/E_n16_2x2__objectives__s1__two_stage/result.json"
    if read(reference)["config"] != observed[-1]["config"]:
        raise ValueError("Model-dimension reference describes a different scheduling configuration")
    observed[-1].update(dimension_source=reference.relative_to(ROOT).as_posix(),dimension_sha256=sha(reference))
    for cell in read(SCREEN / "campaign.json")["cells"]:
        folder = SCREEN / "runs" / cell["id"]
        old = read(folder / "result.json")
        eligible = bool(old.get("original_model_check") and old.get("jobs") and old.get("validation", {}).get("valid"))
        screen.append(dict(case=cell["case"], archived_status=old.get("status"), archived_solutions=old.get("solutions"),
                           measured_in_manuscript=eligible, source=(folder / "result.json").relative_to(ROOT).as_posix()))
        if eligible:
            include("D_" + cell["case"], "D", folder / "solve", "phase1.json", "variables_phase1.json",
                    ["tab:journal-transfer-cn", "tab:journal-transfer-components-cn"])
    if len(screen) != 27 or sum(r["measured_in_manuscript"] for r in screen) != 6:
        raise ValueError("Qualification archive differs from the manuscript's 27 screened / 6 measured instances")
    keys = {(c["backend"], json.dumps(c["config"], sort_keys=True)) for c in observed}
    if len(keys) != len(observed) or len(observed) != 22:
        raise ValueError("Measured instance inventory contains duplicates or omissions")
    return observed, screen
