"""Read-only frozen inputs, global lower bounds and cap-dependent domain sizes."""
import csv
import hashlib
import json
from pathlib import Path


JMS = Path(__file__).resolve().parents[2]
CASES = {f"n{n}_h{h}": (n, h) for n, h in ((2, 3), (4, 3), (8, 3), (16, 3), (16, 10))}
SOURCES = {
    "n2_h3": "results/table4_one_percent_20261124/inputs/D_n2_H3_mixed_dual/input.json",
    "n4_h3": "results/table4_residence100_20261123/inputs/D_n4_H3_mixed_dual/input.json",
    "n8_h3": "results/table4_residence100_20261123/inputs/D_n8_H3_mixed_dual/input.json",
    "n16_h3": "results/table3_mixed16_20261125/input.json",
    "n16_h10": "results/table3_mixed16_20261125/input.json",
}
CONFIG_HASH = {
    2: "84795322edb9a53594a17a4386bfcebd8045e9e0953e82ce868d47f3125f789c",
    4: "d114ac80122368d008da9219388d61344a4c87c0fc1d412c7e1aa176acac1504",
    8: "bf4e62bcd89c8a7d17912ef02ce6cbedd668ba512563f35c35eb929a1d22ea30",
    16: "70a97500b0fb8c41e5f627a8264afafed8e6475104f0b6bc2e60fd18812ea0d6",
}
BOUND_DIR = "results/terminal_unload_20261125/product_bound"
EQUIPMENT = "experiments/terminal_unload_20261125"
BACKEND = "model4_pjob_nonprocessing_20261103"
PROOF_HASHES = {
    f"{BOUND_DIR}/derivation.md": "4d802c0a9a5a622df8fca5e1c62d2824707ba74c658c7391c7f479eac1e95526",
    f"{BOUND_DIR}/n4.json": "e4973b35cc3b13f236edbf7af3cafb15127ea600d07265d4f7a560a7cc37cbef",
    f"{BOUND_DIR}/n8.json": "281b7f8dbcb9844cb9bebaefc9133524852c34e6069d46a82d026cde802177cc",
    f"{EQUIPMENT}/compare_scope.py": "59a265cb4213b08f6e67b00421bac765ad8a37571fe9ac96c0cef0e323e411c6",
    f"{EQUIPMENT}/product_bound.py": "c537885ae8d5472a1fa5ca671800d13dc41f3bb714210869ad70a5c205c21cd2",
    f"{EQUIPMENT}/extended_model.py": "4af1bdb83f3a9f21270323623f9d87ba5cb8221548eed8cd96001a8766e97917",
    "experiments/sublevel_bounds_20261120/bounds.py": "e5235eb9cd4a7a03b456704e84ff2fe0c45b7423d02efaa1e0e87e835698f59e",
    f"{BACKEND}/model.py": "1c098c7073ec09d8d762467d6faab04e7534ea558f60877c3ba1a50d7fb3a2be",
    f"{BACKEND}/joint_pairing_model.py": "58b09bd4da318cb67ca978284475e2369d1328206b9213f715f4d99815092ced",
    f"{BACKEND}/joint_chamber_cycle_model.py": "d52b0f35f8ce90c7d18c15c0eed55069dd569c92f3b24de90cc8c8b6f993cb30",
    "experiments/residence_objective_20261125/primary_relaxation.py": "a896d4e0068d62a3ed2e99bf04fd21b706526eaa7d1f5a59773978a5f2b00cbe",
    "experiments/residence_objective_20261125/tight_primary.py": "7e32bf9a3a74846335278d107b89a684137814b99bd91ed06d5bb0b79df8b968",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def input_folder(key):
    if key not in CASES:
        raise KeyError(key)
    return JMS / "results/lex_campaign_20261127/inputs" / key


def program_sources():
    """Fingerprints for reconstruction, original-row replay, score and the seed-1 CPU policy."""
    paths = ["experiments/lex_campaign_20261127/prepare_inputs.py",
             "experiments/stall_nodes_20261127/phases.py", f"{EQUIPMENT}/extended_model.py",
             "experiments/component_gap_restore_20261119/component.py",
             "experiments/square_residence_20261125/score.py", "experiments/sublevel_bounds_20261120/bounds.py",
             "experiments/finite_budget_20261116/finite_budget.py",
             "experiments/pareto_rl_dmct_20261119/decoder.py", "experiments/pareto_rl_dmct_20261119/common.py"]
    paths.extend("experiments/scale75_20261118/" + f for f in ("packing.py", "patterns.py", "timing.py"))
    paths.extend(f"{BACKEND}/{f}.py" for f in ("model", "joint_pairing_model", "joint_chamber_cycle_model",
                 "seed", "physical_seed", "validate", "physical_validate", "pjobs", "pjob_order",
                 "grippers", "joint_algorithms"))
    paths.extend("../" + f for f in ("scip_imports.py", "cie/code/run_cie_benchmarks.py",
                 "cutsel_agent_parallel.py", "pointer_net.py", "pointer_net_end_token.py", "beam_search.py",
                 "utils.py", "global_const.py", "environments.py", "path_utils.py", "runtime_compat.py",
                 "utilss/mean_std.py", "logger.py", "cie/configs/cie_proposed_inference.json"))
    manifest = "../cie/results/repro_manifest/selected_checkpoint_manifest.csv"
    with (JMS / manifest).open(encoding="utf-8-sig") as src:
        [row] = [r for r in csv.DictReader(src) if r["family"] == "proposed" and r["training_seed"] == "1"]
    paths.extend([manifest, "../" + row["checkpoint"], "../" + row["variant"]])
    hashes = {f: digest(JMS / f) for f in paths}
    if any(hashes["../" + row[k]] != row[k + "_sha256"] for k in ("checkpoint", "variant")):
        raise ValueError("The frozen training-seed-1 network or its variant has changed.")
    return hashes


def case_spec(key):
    """Return JSON-serializable inputs. All stored paths are relative to JMS-version."""
    n, h = CASES[key]
    prep = input_folder(key) / "preparation.json"
    record = read(prep)
    src = JMS / SOURCES[key]
    path = input_folder(key) / "schedule.json"
    if ((n, h, key) != (record["n"], record["h"], record["key"]) or
            digest(src) != CONFIG_HASH[n] or record["source_sha256"] != CONFIG_HASH[n] or
            digest(path) != record["input_sha256"] or
            record["start_schedule"] != path.relative_to(JMS).as_posix()):
        raise ValueError(f"Frozen case or schedule digest changed for {key}.")
    cfg = read(path)["config"]
    if cfg != read(src)["config"] | {"cleaning_interval": h}:
        raise ValueError(f"The decoded configuration differs from the frozen table input: {key}")
    if any(cfg[k] for k in ("max_pairs", "max_cycles")):
        raise ValueError(f"The physical source must have unrestricted candidate indices: {key}")
    scope = {
        f"{BOUND_DIR}/derivation.md": "A, extended unload; product-return routing and full-scope projection",
        f"{EQUIPMENT}/compare_scope.py": "B, extended unload; mean >= (2*handling+2*rotation)*mixed_fraction, other terms nonnegative",
        "experiments/sublevel_bounds_20261120/bounds.py": "Capacity counting only, under a feasible product-return cap; independent of exit orientation",
        f"{EQUIPMENT}/extended_model.py": "Validated equipment domain and process-score model",
        f"{BACKEND}/model.py": "Routing and unrestricted candidate domain in base equipment model",
        f"{BACKEND}/joint_pairing_model.py": "Product/auxiliary label blocks and within-block relabeling",
        f"{BACKEND}/joint_chamber_cycle_model.py": "Each production cycle contains product; at most one cleaning in each gap and one terminal cleaning",
    }
    lower_a = 7 + 28*n + 261
    if n in (4, 8):
        cert = f"{BOUND_DIR}/n{n}.json"
        scope[cert] = f"A, exact {n}-wafer instance; continuous schedules project to integer event schedules"
        scope[f"{EQUIPMENT}/product_bound.py"] = "A, optional product-first terminal unload reflected in relaxed rear-side timing"
        projection = read(JMS / cert)
        lower_a = projection["projection_lower"]
        witness = ("results/terminal_unload_20261125/scope/four_order/schedule.json" if n == 4
                   else "results/terminal_unload_20261125/eight_event_replay/H3/schedule.json")
        if projection["signature"] != [digest(JMS / witness), PROOF_HASHES[f"{EQUIPMENT}/product_bound.py"]]:
            raise ValueError(f"The archived projection signature is invalid for {key}.")
        # The witness is used only by the archival projection to test coverage.
        # Its inventory and physical conditions identify this proof's domain.
        historical = read(JMS / witness)["config"]
        if any(cfg[k] != historical[k] for k in cfg if k not in ("max_pairs", "max_cycles")):
            raise ValueError(f"The projection was computed for a different physical configuration: {key}")
        for f in ("primary_relaxation", "tight_primary"):
            scope[f"experiments/residence_objective_20261125/{f}.py"] = "Hash-pinned source of amended product projection"
    proofs = []
    for name, domain in scope.items():
        if digest(JMS / name) != PROOF_HASHES[name]:
            raise ValueError(f"Archived proof or model differs: {name}")
        proofs.append(dict(path=name, sha256=PROOF_HASHES[name], scope=domain))
    mix = sum(products["2x2"] for products in cfg["load_ports"].values())
    lower_b = (2*cfg["handling"] + 2*cfg["rotation"]) * mix / n
    programs = program_sources()
    if (programs["experiments/lex_campaign_20261127/prepare_inputs.py"] != record["program_sha256"] or
            programs["experiments/pareto_rl_dmct_20261119/decoder.py"] != record["decoder_sha256"]):
        raise ValueError(f"Decoder or preparation program changed for {key}.")
    return dict(key=key, n=n, h=h, start_schedule=record["start_schedule"],
                input_sha256=record["input_sha256"], lb_A=lower_a, lb_B=lower_b,
                proof_sources=proofs, program_sources=programs, config=cfg, capacity=record["capacity"],
                start_score=record["score"], preparation=prep.relative_to(JMS).as_posix(),
                preparation_sha256=digest(prep), preparation_seconds=record["elapsed_s"],
                start_assignment=None, start_assignment_sha256=None)
