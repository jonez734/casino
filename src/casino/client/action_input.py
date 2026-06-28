# casino/client/action_input.py
# Tab-completion helpers for in-game action input.

from __future__ import annotations

from bbsengine6.io.inputstring import Completer


def resolve_action(input_str: str, actions: list[dict]) -> str | None:
    """Resolve user input to action, handling ambiguous matches.

    Args:
        input_str: User input (hotkey prefix or action name)
        actions: List of action dicts with 'action', 'label', 'hotkey' keys

    Returns:
        Action name if unambiguous, None if no match,
        Raises ValueError if ambiguous (multiple matches)
    """
    if not input_str:
        return None

    input_lower = input_str.lower()

    # First check exact hotkey match
    for action in actions:
        if action.get("hotkey", "").lower() == input_lower:
            return action["action"]

    # Then check prefix match on action names
    matches = [a for a in actions if a["action"].lower().startswith(input_lower)]

    if len(matches) == 0:
        return None

    if len(matches) == 1:
        return matches[0]["action"]

    # Multiple matches - raise error with action names
    options = ", ".join([a["action"] for a in matches])
    raise ValueError(f"Which actions? {options}")


class ActionInputHandler(Completer):
    """Handler for action input with tab completion support."""

    def __init__(self, actions: list[dict]):
        super().__init__()
        self.actions = actions
        self.action_map = {}
        for a in actions:
            self.action_map[a.get("hotkey", "").lower()] = a["action"]
            self.action_map[a["action"].lower()] = a["action"]

    def resolve(self, input_str: str) -> str | None:
        """Resolve input to action name."""
        return resolve_action(input_str, self.actions)

    def get_matches(self, prefix: str, **kwargs) -> list[str]:
        """Return list of possible completions for the prefix.

        Matches against both action names and hotkeys.
        """
        if not prefix:
            return [a["action"] for a in self.actions]

        prefix_lower = prefix.lower()
        matches = []

        for a in self.actions:
            if a["action"].lower().startswith(prefix_lower) or a.get("hotkey", "").lower() == prefix_lower:
                matches.append(a["action"])

        return sorted(set(matches))

    def get_completer(self) -> ActionInputHandler:
        """Return self for use as completer with inputstring."""
        return self
