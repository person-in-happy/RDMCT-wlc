import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
OUT = JMS / "results/table3_pure16_20261125"
LEVELS = {"10pct": .10, "1pct": .01, "0p01pct": .0001}

def load(path):
    return json.loads(Path(path).read_bytes())

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf8")
    os.replace(temp, path)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def setup():
    sys.path.insert(0, str(HERE.parent/"manuscript_projection_20261120"))
    import cell
    sys.path.insert(0, str(cell.BACKENDS["D"]))
    sys.path.insert(0, str(HERE.parent/"pareto_rl_dmct_20261119"))
    return cell

def config(recipe):
    from model import Config
    ports = {f"LP{i}": {m:4 * (m==recipe) for m in ["4x1", "2x2"]} for i in range(1,5)}
    return Config(load_ports=ports, cleaning_interval=10, dummy_count=8, horizon=100000)
