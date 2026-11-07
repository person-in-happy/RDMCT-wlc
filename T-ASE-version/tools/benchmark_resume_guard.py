"""Guard the existing benchmark's JSONL recovery without editing its active launcher."""
from pathlib import Path
import datetime
import shutil
import sys
import uuid

from resumable_experiments import ROOT, repair_checkpoint_tail


def guarded_load(loader, path, signature, campaign):
    path = Path(path)
    others = [p for p in path.parent.glob("*.jsonl") if p != path]
    if others:
        raise RuntimeError("Checkpoint signature changed; refusing a new benchmark in the same batch: "
                           + ", ".join(str(p) for p in others))
    if path.exists():
        repair_checkpoint_tail(path)
    rows, complete = loader(path, signature)
    artifacts = (complete or {}).get("artifacts") or []
    if not artifacts or not all(Path(p).is_file() for p in artifacts):
        # A failed attempt may already have written partial summary files.
        # Preserve them outside runs/, where recursive analyzers would double-count.
        reports = [p for p in path.parent.parent.iterdir()
                   if p.is_file() and p.suffix in {".json", ".csv", ".md"}]
        if reports:
            archive = (campaign / "attempt_history" / path.parent.parent.name /
                       (datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]))
            archive.mkdir(parents=True)
            for report in reports:
                shutil.move(str(report), str(archive / report.name))
    return rows, complete


def main():
    sys.path.insert(0, str(ROOT / "cie/code"))
    import run_cie_benchmarks as benchmark
    load = benchmark._load_checkpoint

    def checked_load(path, signature):
        output = Path(path).parent.parent
        campaign = output.parent.parent
        return guarded_load(load, path, signature, campaign)

    benchmark._load_checkpoint = checked_load
    benchmark.main()


if __name__ == "__main__":
    main()

