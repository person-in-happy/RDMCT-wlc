"""Resume the fixed-structure Huber search with its own solver and score hashes."""
import runpy
from supplement import PREVIOUS

if __name__ == "__main__":
    runpy.run_path(str(PREVIOUS/"supplement_checkpoint.py"),run_name="__main__")
