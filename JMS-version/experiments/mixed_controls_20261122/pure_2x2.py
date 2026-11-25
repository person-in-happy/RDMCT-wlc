"""Extend the matched threshold grid with pure 2x2 recipes at both batch sizes."""
import sys
from pathlib import Path

from scale import CP, LEVELS, OUT, Config, execute, first, prepare, product_solve, read, save, sha

BASE = OUT / "grid_2x2"


def prepare_input(size):
    from decoder import Decoder, Retiming

    folder = BASE / "inputs" / str(size)
    if (folder / "prepared/primary.json").exists():
        return
    counts = (2, 0, 0, 0) if size == 2 else (1, 1, 1, 1)
    ports = {f"LP{i}": {"4x1": 0, "2x2": count} for i, count in enumerate(counts, 1)}
    cfg = Config(load_ports=ports, cleaning_interval=2 if size == 2 else 10,
                 dummy_count=4 if size == 2 else 8)
    decoder = Decoder(cfg)
    genes = tuple(x for i in range(size) for x in (0, i // 2 % 2, 0, 0, 0))
    batch = decoder.build(genes, decoder.pairing(genes))
    schedule = Retiming(batch, 25).solve("A", None, 5)
    prepare(folder, cfg, schedule, 1)


def run(size, a, folder):
    source = BASE / "inputs" / str(size) / "prepared"
    primary = folder / "A"
    if not (primary / "primary.json").exists():
        first(source, primary, size, 1, "default", "cp", None, LEVELS[a], True)
    record = read(primary / "primary.json")["record"]
    assert record["gate"] and record["gap"] <= LEVELS[a] + 1e-9
    results = {}
    for b, threshold in LEVELS.items():
        endpoint = product_solve(folder / b, primary / "schedule.json", primary / "assignment.json.gz",
                                 "D", size, 1, "fixed", gap=threshold)
        assert endpoint["eligible"] and endpoint["replay"]["valid"]
        results[b] = dict(metrics=endpoint["measured"], record=endpoint["record"])
    save(folder / "result.json", dict(case=f"D_n{size}_pure_2x2", size=size, a=a,
         start=sha(source / "assignment.json.gz"), primary=record, results=results))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run(int(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
    else:
        jobs = []
        for size in (2, 4):
            print(f"Preparing {size}-wafer start", flush=True)
            prepare_input(size)
            for a in LEVELS:
                path = str(BASE / f"n{size}__{a}")
                jobs.append((CP, __file__, [str(size), a, path], path))
        sys.exit(execute(jobs, 3, BASE))
