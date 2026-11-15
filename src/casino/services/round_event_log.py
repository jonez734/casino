"""A headless subscriber that logs a round's events (slice 6, the first front end on the seam).

It reads the shared GameService's event domain through its own subscription and writes one log line per
event, in order. It has no wire effect: it never sends to a client. A bot, a test client, or an operator's
log can use the same pattern.
"""

from __future__ import annotations

from typing import Any


class RoundEventLog:
    def __init__(self, service: Any, sink: Any) -> None:
        self._service = service
        self._sink = sink
        self._subscription = service.subscribe_events()

    def drain(self) -> int:
        """Log every event this subscriber has not read yet. Returns how many were logged."""
        events = self._service.read_events(self._subscription)
        for e in events:
            self._sink.info("round event %s table=%s moniker=%s payload=%s",
                            e.kind, e.scope, e.moniker, dict(e.payload))
        return len(events)
