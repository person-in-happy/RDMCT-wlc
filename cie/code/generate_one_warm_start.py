"""Generate one exact-instance SPBS warm start for parallel recovery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from petri_mip_generator import PetriMIPConfig
from petri_warm_start import find_compatible_mixed_warm_start, write_mixed_warm_start


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--time_limit", type=float, default=3600.0)
    parser.add_argument("--memory_limit_mb", type=float, default=2048.0)
    parser.add_argument("--random_seed", type=int, default=1)
    args = parser.parse_args()

    instance = Path(args.instance).resolve()
    if not instance.is_file():
        raise FileNotFoundError(instance)
    sidecar = instance.with_name(f"{instance.stem}.cie.json")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    cfg = PetriMIPConfig(**payload["config"])
    if float(cfg.max_module_residency_time) != 500.0:
        raise RuntimeError(
            f"Expected max_module_residency_time=500, got {cfg.max_module_residency_time}"
        )

    cached = find_compatible_mixed_warm_start(str(instance.parent), instance.name)
    if cached:
        print(f"cached: {cached}", flush=True)
        return
    result = write_mixed_warm_start(
        str(instance.parent), instance.name, cfg,
        time_limit=args.time_limit,
        memory_limit_mb=args.memory_limit_mb,
        random_seed=args.random_seed,
    )
    if not result:
        raise RuntimeError(
            f"No warm start found for {instance.name} with seed {args.random_seed}"
        )
    print(f"generated: {result}", flush=True)


if __name__ == "__main__":
    main()
