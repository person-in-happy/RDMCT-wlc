"""Prepare five deterministic, independent decoder starts before lexicographic search."""
import json
import os
import sys
import time
import warnings
from pathlib import Path

from inputs import CASES, JMS, SOURCES, digest, input_folder, read

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
sys.path.insert(0, str(JMS / "experiments/pareto_rl_dmct_20261119"))
import decoder
from common import Config
from scipy.optimize import OptimizeWarning
from validate import validate
sys.path.insert(0, str(JMS / "experiments/sublevel_bounds_20261120"))
from bounds import capacity
sys.path.insert(0, str(JMS / "experiments/square_residence_20261125"))
from score import metrics


def write(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf8")
    temp.replace(path)


# scipy passes unrecognised options to HiGHS. Pin its own worker count,
# independently of the BLAS environment or this machine's CPU count.
scipy_linprog = decoder.linprog


def linprog_one_thread(*args, options, **kwargs):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Unrecognized options detected.*", category=OptimizeWarning)
        return scipy_linprog(*args, options={**options, "threads": 1}, **kwargs)


def prepare(key):
    from inputs import case_spec
    folder = input_folder(key)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "preparation.json").exists():
        print(f"{key} existing validated input {case_spec(key)['input_sha256']}", flush=True)
        return
    start = time.monotonic()
    n, h = CASES[key]
    source_path = JMS / SOURCES[key]
    frozen = read(source_path)["config"]
    cfg = Config(**(frozen | {"cleaning_interval": h}))
    if cfg.max_pairs or cfg.max_cycles:
        raise ValueError("The input is structurally capped.")
    dec = decoder.Decoder(cfg)
    candidates = []
    trials = []
    for layout in ("by_recipe", "alternate_pairs", "one_chamber"):
        elapsed = time.monotonic()
        genes = tuple(v for i in range(n) for v in
                      (0, {"by_recipe": int(i >= n // 2), "alternate_pairs": i // 2 % 2,
                           "one_chamber": 0}[layout], 0, 0, 0))
        batch = dec.build(genes, dec.pairing(genes))
        schedule = decoder.Retiming(batch, 25).solve("A", None, 20)
        checks = validate(schedule) if schedule else {}
        score = metrics(schedule) if checks.get("valid") else {}
        trials.append(dict(layout=layout, elapsed_s=time.monotonic()-elapsed,
                           physical_checks=checks.get("checks", 0), valid=bool(checks.get("valid")),
                           score=score, errors=checks.get("errors", [])))
        if checks.get("valid"):
            # Tie-break by the fixed layout order, independent of subsequent stages.
            candidates.append((score["cmax"], len(trials), layout, schedule, score))
    if not candidates:
        raise ValueError(f"No physically valid decoder start for {key}: {trials}")
    _, _, layout, schedule, score = min(candidates, key=lambda item: item[:2])
    schedule_path = folder / "schedule.json"
    write(schedule_path, schedule)
    plan = capacity(cfg, score["cmax"])
    rec = dict(key=key, n=n, h=h, source=SOURCES[key], source_sha256=digest(source_path),
               preparation="three fixed gene layouts + continuous LP, smallest valid makespan",
               spbs_in_preparation=False, threads=1, lp_seconds_per_layout=20,
               selected=layout, trials=trials, score=score, capacity=plan,
               start_schedule=schedule_path.relative_to(JMS).as_posix(),
               input_sha256=digest(schedule_path), elapsed_s=time.monotonic()-start,
               program_sha256=digest(Path(__file__)), decoder_sha256=digest(Path(decoder.__file__)))
    write(folder / "preparation.json", rec)
    print(f"{key} {layout} A={score['cmax']:.3f} B={score['secondary']:.3f} "
          f"P={plan['pairs']} Q={plan['cycles']} elapsed={rec['elapsed_s']:.3f}s", flush=True)


if __name__ == "__main__":
    decoder.linprog = linprog_one_thread
    for case in CASES:
        prepare(case)
