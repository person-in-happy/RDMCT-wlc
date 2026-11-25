"""Test simultaneous attainability of the two proven eight-wafer objective minima."""
import argparse
import hashlib
import json
from pathlib import Path
from tight_primary import cp_model, tightened


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=120)
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    source = json.loads(args.source.read_bytes())
    native = sorted((w for w in source["jobs"] if w["product"]),
                    key=lambda w: (w["pjob"], w["pjob_index"]))
    modes = {p["id"]:p["mode"] for p in source["pairs"]}
    assert [modes[w["pair"]] for w in native].count("2x2") == len(native)/2 == 4
    relaxation = tightened(source, 553)
    variables = {v.name:relaxation.get_int_var_from_proto_index(i) for i,v in enumerate(relaxation.proto.variables)}
    for i,w in enumerate(native):
        # Equality in mean+D+E >= .5*(7-D)+D+E forces D=E=0,
        # and then every full wafer has residence 0, every mixed wafer residence 7.
        # These are integer differences, preserved by flooring native event times.
        required = 7 if modes[w["pair"]] == "2x2" else 0
        relaxation.add(variables[f"{i}_unload"] - variables[f"{i}_load"] == 181 + required)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 3
    solver.parameters.max_time_in_seconds = args.budget
    solver.parameters.log_search_progress = True
    solver.parameters.log_to_stdout = False
    with (args.out/"cp.log").open("w", encoding="utf8", buffering=1) as log:
        solver.log_callback = lambda value: log.write(value.rstrip()+"\n")
        status = solver.solve(relaxation)
    result = dict(status=solver.status_name(status), cmax_cap=553, fB_required=3.5,
                  wall_s=solver.wall_time, branches=solver.num_branches, workers=3,
                  source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
                  code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                               (Path(__file__),Path(__file__).with_name("tight_primary.py"),
                                Path(__file__).with_name("primary_relaxation.py"))})
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        result["projected_only"] = {name:solver.value(var) for name,var in variables.items()
                                    if name.startswith(("w","use","full","start","ch"))
                                    or name[0].isdigit() or name=="makespan"}
        result["identities"] = [w["identity"] for w in native]
    (args.out/"result.json").write_text(json.dumps(result,indent=2), encoding="utf8")
    print(result,flush=True)
