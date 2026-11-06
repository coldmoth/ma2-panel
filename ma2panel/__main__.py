"""Run the stable launcher with ``python -m ma2panel``."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent.parent / "bridge.py"), run_name="__main__")
