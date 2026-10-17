"""Render the preserved strict-4s variants from the verified manifest."""
from pathlib import Path
import runpy
if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("render_temp_4s.py")), run_name="__main__")
