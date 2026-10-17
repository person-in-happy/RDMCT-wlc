"""Figure 2 uses Figure 1 geometry with atmospheric dummy storage beside LP4."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "figures"))
from generate_process_figures import system_topology

if __name__ == "__main__":
    for lang in ("cn", "en"):
        system_topology(lang, single_source=True)
