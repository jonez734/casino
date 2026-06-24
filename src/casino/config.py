import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def get_package_data_path(filename: str) -> Path:
    """Get path to a file in the casino package data directory."""
    return Path(__file__).parent / "data" / filename


def load_bed_defaults() -> Dict[str, Any]:
    """Load default configuration from bed.json package data."""
    bed_json_path = get_package_data_path("bed.json")
    if bed_json_path.exists():
        with open(bed_json_path) as f:
            return json.load(f)
    return {}


def load_config(
    config_file: Optional[str] = None,
    env_prefix: str = "CASINO_",
    **overrides: Any,
) -> Dict[str, Any]:
    """
    Load casino configuration with priority order:
    1. Command line / overrides (highest)
    2. Config file (if provided)
    3. bed.json defaults (lowest)
    
    Environment variables override defaults.
    Variable format: CASINO_POSTOFFICE_ENABLED=true
    """
    config = load_bed_defaults()
    
    if config_file and os.path.exists(config_file):
        with open(config_file) as f:
            file_config = json.load(f)
            config = _merge_config(config, file_config)
    
    env_config = _load_from_env(env_prefix)
    config = _merge_config(config, env_config)
    
    config = _merge_config(config, overrides)
    
    return config


def _merge_config(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge override into base config."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _load_from_env(prefix: str) -> Dict[str, Any]:
    """Load configuration from environment variables.
    
    Variable format: CASINO_<SECTION>_<KEY>=value or CASINO_KEY=value
    Example: CASINO_POSTOFFICE_ENABLED=true, CASINO_DEBUG=true
    """
    config = {}
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        
        config_key = key[len(prefix):]
        
        if "_" in config_key:
            parts = config_key.split("_", 1)
            section = parts[0].lower()
            key_name = parts[1].lower()
            
            if section not in config:
                config[section] = {}
            
            if value.lower() in ("true", "false"):
                config[section][key_name] = value.lower() == "true"
            elif value.isdigit():
                config[section][key_name] = int(value)
            else:
                config[section][key_name] = value
        else:
            key_name = config_key.lower()
            if value.lower() in ("true", "false"):
                config[key_name] = value.lower() == "true"
            elif value.isdigit():
                config[key_name] = int(value)
            else:
                config[key_name] = value
    
    return config


def get_postoffice_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get postoffice configuration, loading defaults if not provided."""
    if config is None:
        config = load_config()
    return config.get("postoffice", {})


def reload_config() -> Dict[str, Any]:
    """Reload configuration from bed.json, ignoring any overrides."""
    return load_bed_defaults()
