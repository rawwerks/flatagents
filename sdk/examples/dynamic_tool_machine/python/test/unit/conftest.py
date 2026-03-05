import sys
from pathlib import Path

# Add the example's src directory so tools module is importable without install
_src = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_src))
