import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "dialogs_config.yaml"

try:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
except FileNotFoundError:
    logger.error(f"Dialogs config not found at {CONFIG_PATH}")
    raise

# Expose the full parsed YAML for things like patterns
RAW_CONFIG = raw

# Pull out just the events mapping for your reminder flows
DIALOGS = RAW_CONFIG.get("events", {})

# Validate each event has required keys
for key, cfg in DIALOGS.items():
    if "chat_id" not in cfg:
        logger.error(f"[DIALOGS LOADER] Missing `chat_id` for event '{key}'")
        raise KeyError(f"Missing `chat_id` for event '{key}'")
    if "trigger" not in cfg:
        logger.error(f"[DIALOGS LOADER] Missing `trigger` for event '{key}'")
        raise KeyError(f"Missing `trigger` for event '{key}'")
