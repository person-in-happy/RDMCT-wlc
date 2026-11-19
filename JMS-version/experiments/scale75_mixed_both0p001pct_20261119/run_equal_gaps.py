"""Rerun the original 75-wafer mixed case with a 0.001% solver gap for both objectives."""
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scale75_mixed_two_gaps_20261119"))
import run_mixed

RELATIVE_GAP = 0.00001  # 0.001 percent, expressed as the solver's fraction.
OUT = run_mixed.old.JMS / "results" / "scale75_mixed_A0p001pct_B0p001pct_D_20261119"


def main():
    original_protocol = run_mixed.primary.protocol

    def protocol():
        spec = original_protocol()
        for path in (Path(__file__), HERE / "control.ps1"):
            key = path.relative_to(run_mixed.old.JMS.parent).as_posix()
            spec["source_sha256"][key] = run_mixed.old.digest(path)
        return spec

    with (
        patch.multiple(run_mixed, A_GAP=RELATIVE_GAP, B_GAP=RELATIVE_GAP, OUT=OUT),
        patch.object(run_mixed.primary, "protocol", protocol),
    ):
        run_mixed.main()


if __name__ == "__main__":
    main()
