"""
casino.startup.checkchannels - apply casino-specific channel overrides.

Runs after ``bbsengine6.startup.main`` lands the channel schema (via
``checkchannel``) and after the engine auto-seed step populates any
modules-named channels. Reads ``args._casino_config`` for the optional
``channel_overrides`` and ``channel_creator`` keys and applies them.

Failure policy (option b from the planning phase): if no
``channel_creator`` is configured, emit a warning and continue. The
engine-level auto_seed in bbsengine6 handles the canonical channels
(``casino:global``, ``system:announcements``); casino overrides are a
secondary mechanism for per-deployment tuning (e.g. adding a casino
announcer who should be able to push to ``system:announcements``).
"""

from typing import Any, Dict, Optional

from bbsengine6 import io
from bbsengine6.member.lib import is_namespaced_moniker, moniker_exists
from bbsengine6.services.channel import ChannelService


def _apply_overrides(
    args: Any, overrides: list, conn: Optional[Any] = None
) -> bool:
    """Apply a list of override dicts to the channel configuration.

    Each override is one of:

    - ``{"action": "set_announce_only", "channel": str, "value": bool}``
    - ``{"action": "add_announcer", "channel": str, "moniker": str,
       "actor": str}``
    - ``{"action": "remove_announcer", "channel": str, "moniker": str,
       "actor": str}``

    ``actor`` must be namespaced (or a known sysop); the underlying
    ``ChannelService`` permission checks handle the rest.

    Returns True if all overrides applied (or were no-ops), False on
    any hard failure. Soft failures (e.g. channel not found) are
    warned and skipped so one bad override does not abort the others.
    """
    if not overrides:
        return True

    service = ChannelService(args)
    ok = True
    for entry in overrides:
        if not isinstance(entry, dict):
            io.echo(
                f"casino checkchannels: override entry is not a dict: {entry!r}",
                level="warning",
            )
            continue
        action = entry.get("action")
        channel = (entry.get("channel") or "").strip()
        if not channel:
            io.echo(
                f"casino checkchannels: override missing channel: {entry!r}",
                level="warning",
            )
            continue
        try:
            if action == "set_announce_only":
                result = service.set_announce_only(
                    channel_name=channel,
                    value=bool(entry.get("value", False)),
                    by_moniker=entry.get("actor"),
                )
            elif action == "add_announcer":
                result = service.add_announcer(
                    channel_name=channel,
                    moniker=entry.get("moniker", ""),
                    addedby=entry.get("actor"),
                )
            elif action == "remove_announcer":
                result = service.remove_announcer(
                    channel_name=channel,
                    moniker=entry.get("moniker", ""),
                    actor_moniker=entry.get("actor"),
                )
            else:
                io.echo(
                    f"casino checkchannels: unknown action {action!r}; skipping",
                    level="warning",
                )
                continue
            if not result.get("success"):
                io.echo(
                    f"casino checkchannels: override {entry!r} failed: "
                    f"{result.get('message')!r}",
                    level="warning",
                )
        except Exception:
            io.echo_traceback(
                f"casino checkchannels: override {entry!r} raised:"
            )
            ok = False
    return ok


def main(args: Any, **kwargs) -> bool:
    """Apply casino channel overrides from ``args._casino_config``.

    Mirrors the option-b (warn-and-skip) policy: missing
    ``channel_creator`` is a warning, not a failure. ``channel_overrides``
    apply only when the creator moniker exists and is namespaced.
    """
    casino_cfg = getattr(args, "_casino_config", None) or {}
    if not isinstance(casino_cfg, dict):
        return True

    creator = (casino_cfg.get("channel_creator") or "").strip()
    if not creator:
        io.echo(
            "casino checkchannels: no channel_creator configured; "
            "skipping casino-specific channel overrides. "
            "Set casino.channel_creator in bed.json to enable.",
            level="info",
        )
        return True

    if not is_namespaced_moniker(creator):
        io.echo(
            f"casino checkchannels: channel_creator {creator!r} is not "
            f"namespaced; this is allowed but unusual. Namespacing is the "
            f"recommended convention.",
            level="info",
        )

    if not moniker_exists(args, creator):
        io.echo(
            f"casino checkchannels: channel_creator {creator!r} does not "
            f"exist in engine.__member; the engine-level auto_seed step "
            f"will create it on next BED start if needed. Skipping "
            f"casino-specific overrides for now.",
            level="warning",
        )
        return True

    overrides = casino_cfg.get("channel_overrides") or []
    if not isinstance(overrides, list):
        io.echo(
            f"casino checkchannels: channel_overrides must be a list, "
            f"got {type(overrides).__name__}; skipping",
            level="warning",
        )
        return True

    return _apply_overrides(args, overrides, conn=kwargs.get("conn"))
