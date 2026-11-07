"""Resume model-size measurements using the original implementation."""
from pathlib import Path
import sys

from resumable_experiments import ROOT, assert_idle, campaign_lock, repair_checkpoint_tail


def main():
    sys.path.insert(0, str(ROOT / "cie/code"))
    import analyze_cie_model_scale as scale
    args = scale._parse_args()
    out = Path(args.output_dir).resolve()
    assert_idle(out, "model-scale")
    out.mkdir(parents=True, exist_ok=True)
    with campaign_lock(out):
        original = scale._checkpoint_rows

        def guarded(path, signature):
            others = [p for p in path.parent.glob("model_scale_*.jsonl") if p != path]
            if others:
                raise RuntimeError("Model-scale signature changed; use a new output directory.")
            if path.exists():
                repair_checkpoint_tail(path)
            return original(path, signature)

        scale._checkpoint_rows = guarded
        scale.main()


if __name__ == "__main__":
    main()

