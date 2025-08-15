# pillsbot/tests/conftest.py
import sys
from pathlib import Path

# This file is at <project_root>/pillsbot/tests/conftest.py
# Project root is two levels up from here.
ROOT = Path(__file__).resolve().parents[2]  # -> /home/igor/med
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
