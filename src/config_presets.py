from __future__ import annotations

import copy
import json
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("data/erc_configs2.json")


def load_config_bundle(path: str | Path = DEFAULT_CONFIG_PATH) -> list[dict]:
    """Load a config bundle and return independent config dictionaries."""
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    configs = raw.get("configs", []) if isinstance(raw, dict) else raw
    if not isinstance(configs, list):
        raise ValueError("ERC config bundle must contain a list of configs.")
    if any(not isinstance(config, dict) for config in configs):
        raise ValueError("Every ERC config must be a JSON object.")
    return copy.deepcopy(configs)


def load_preset_configs(path: str | Path = DEFAULT_CONFIG_PATH) -> list[dict]:
    """Load webpage presets and make their end date track the latest data."""
    presets = load_config_bundle(path)
    for config in presets:
        config["auto_end_date"] = True
        config["_preset"] = True
    return presets

def load_default_preset(path: str | Path = DEFAULT_CONFIG_PATH) -> dict:
    """Return the configured default preset, falling back to the first preset."""
    presets = load_preset_configs(path)
    if not presets:
        raise ValueError("ERC preset bundle is empty.")

    defaults = [config for config in presets if config.get("default") is True]
    if len(defaults) > 1:
        raise ValueError("ERC preset bundle must contain at most one default config.")
    return copy.deepcopy(defaults[0] if defaults else presets[0])
