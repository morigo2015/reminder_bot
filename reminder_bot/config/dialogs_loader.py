import yaml
from pathlib import Path

# Load raw YAML configuration
CONFIG_PATH = Path(__file__).parent / "dialogs_config.yaml"
with CONFIG_PATH.open("r", encoding="utf-8") as f:
    _RAW = yaml.safe_load(f)

# Expose raw patterns as strings
RAW_PATTERNS = _RAW.get("patterns", {})

# Expose full raw config for messages, events, timings
DIALOGS = _RAW