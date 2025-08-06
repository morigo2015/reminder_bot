import os
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "dialogs.yaml")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)
