from __future__ import annotations

import sys
from pathlib import Path


RL_SAT_ROOT = Path(__file__).resolve().parents[1]
if str(RL_SAT_ROOT) not in sys.path:
    sys.path.insert(0, str(RL_SAT_ROOT))
