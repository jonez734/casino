import os
from typing import Any, Optional


def get_package_data_path(filename: str) -> str:
    """Get path to a file in the casino package data directory."""
    from pathlib import Path
    return str(Path(__file__).parent / "data" / filename)


def load_config(
    config_file: Optional[str] = None,
    env_prefix: str = "CASINO_",
    **overrides: Any,
) -> dict[str, Any]:
    """
    Load casino configuration with priority order:
    1. Command line / overrides (highest)
    2. Config file (if provided)
    3. Environment variables
    4. Empty defaults (lowest)

    Environment variables override defaults.
    Variable format: CASINO_POSTOFFICE_ENABLED=true
    """
    config: dict[str, Any] = {}

    if config_file and os.path.exists(config_file):
        import json
        with open(config_file) as f:
            file_config = json.load(f)
            config = _merge_config(config, file_config)

    env_config = _load_from_env(env_prefix)
    config = _merge_config(config, env_config)

    config = _merge_config(config, overrides)

    return config


def _merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge override into base config."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _load_from_env(prefix: str) -> dict[str, Any]:
    """Load configuration from environment variables.

    Variable format: CASINO_<SECTION>_<KEY>=value or CASINO_KEY=value
    Example: CASINO_POSTOFFICE_ENABLED=true
    """
    config: dict[str, Any] = {}
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


def get_casino_config(args: Any) -> dict[str, Any]:
    """Return the casino config block, sourced from bed.json when wired.

    The bed runtime is expected to attach the merged ``casino`` block
    from ``bed.json`` to the args namespace under ``_casino_config``
    during bring-up (see :class:`casino.api.handler.MessageRouter._bootstrap_casino_config`).
    When that's not wired (door-mode / standalone tests), this falls
    back to a fresh :func:`load_config` read of an explicit
    ``casino.json`` path (``args._casino_config_file``) and extracts
    the ``casino`` section, and finally to empty defaults.

    The returned dict is the casino-level block (typically ``{"blackjack":
    {...}, "stats": {...}}``); game-level helpers like
    :func:`get_surrender_multiplier` dig into it.
    """
    cfg = getattr(args, "_casino_config", None)
    if cfg:
        return cfg
    config_file = getattr(args, "_casino_config_file", None)
    if config_file:
        loaded = load_config(config_file=config_file)
        casino = loaded.get("casino") if isinstance(loaded, dict) else None
        if isinstance(casino, dict):
            return casino
    return {}


def get_surrender_multiplier(args: Any) -> float:
    """Surrender forfeit fraction from ``bed.json`` casino.blackjack.

    Defaults to ``0.5`` — the universal standard in regulated casinos
    (Las Vegas Strip, Atlantic City, Macau). The full bet is returned
    when surrender is unavailable (``surrender_multiplier`` set to
    ``0`` or ``surrender_allowed`` set to ``False``).
    """
    cfg = get_casino_config(args)
    bj = cfg.get("blackjack", {}) if isinstance(cfg, dict) else {}
    allowed = bj.get("surrender_allowed", "early")
    if allowed is False or allowed == "none":
        return 0.0
    try:
        mult = float(bj.get("surrender_multiplier", 0.5))
    except (TypeError, ValueError):
        mult = 0.5
    return mult if 0.0 <= mult <= 1.0 else 0.5


DEFAULT_MAX_TURN_SECONDS = 120
MAX_TURN_SECONDS_CEILING = 3600


def get_max_turn_seconds(args: Any) -> int:
    """Sysop ceiling for a table's ``turn_seconds`` (the play clock), from ``casino.clock``.

    Defaults to ``120``. ``0`` disables the play clock on every table. Values are clamped to
    ``0..3600``; a non-integer falls back to the default.
    """
    cfg = get_casino_config(args)
    clock = cfg.get("clock", {}) if isinstance(cfg, dict) else {}
    try:
        value = int(clock.get("max_turn_seconds", DEFAULT_MAX_TURN_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_MAX_TURN_SECONDS
    return max(0, min(value, MAX_TURN_SECONDS_CEILING))



#: Defaults for the slots big-win announcement. ``enabled`` keeps the shout on; ``multiplier`` is
#: the payout, as a multiple of the bet, that counts as a big win.
BIG_WIN_DEFAULTS: dict[str, Any] = {"enabled": True, "multiplier": 50}


def get_big_win_settings(args: Any) -> dict[str, Any]:
    """Big-win announcement settings from ``bed.json`` casino.slots.big_win.

    Returns ``{"enabled": bool, "multiplier": int}``. Missing or invalid values fall back to
    :data:`BIG_WIN_DEFAULTS`. A multiplier below 1 is rejected, since it would announce every
    winning spin.
    """
    cfg = get_casino_config(args)
    slots = cfg.get("slots", {}) if isinstance(cfg, dict) else {}
    block = slots.get("big_win", {}) if isinstance(slots, dict) else {}
    if not isinstance(block, dict):
        block = {}

    enabled = block.get("enabled", BIG_WIN_DEFAULTS["enabled"])
    if not isinstance(enabled, bool):
        enabled = BIG_WIN_DEFAULTS["enabled"]

    multiplier = block.get("multiplier", BIG_WIN_DEFAULTS["multiplier"])
    if isinstance(multiplier, bool) or not isinstance(multiplier, int) or multiplier < 1:
        multiplier = BIG_WIN_DEFAULTS["multiplier"]

    return {"enabled": enabled, "multiplier": multiplier}
