"""The core casino package does not need tkinter or Pillow; the Tk UI does, and it is separate.

The core is imported with tkinter and PIL blocked. The Tk package is checked for its own
requirements. Card art is never shipped: its location comes from CASINO_CARD_ART.
"""

import importlib
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2]


def _run_without(modules: tuple[str, ...], code: str) -> subprocess.CompletedProcess:
    """Run code in a fresh interpreter where the named top-level modules cannot be imported."""
    blocker = textwrap.dedent(f"""
        import sys
        class _Block:
            def find_spec(self, name, path=None, target=None):
                if name.split('.')[0] in {modules!r}:
                    raise ImportError('blocked for test: ' + name)
                return None
        sys.meta_path.insert(0, _Block())
    """)
    return subprocess.run(
        [sys.executable, "-c", blocker + textwrap.dedent(code)],
        cwd=str(SRC), capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(SRC)},
    )


def test_core_casino_imports_without_tkinter_or_pil():
    result = _run_without(("tkinter", "PIL"), "import casino.lib\nprint('core ok')\n")
    assert result.returncode == 0, result.stderr
    assert "core ok" in result.stdout


def test_core_lib_has_no_tk_classes():
    result = _run_without(
        ("tkinter", "PIL"),
        "import casino.lib as l\nprint(hasattr(l, 'tkCard'), hasattr(l, 'tkHand'), hasattr(l, 'tkTable'))\n",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False False"


def test_tk_package_loads_when_its_requirements_are_present():
    pytest.importorskip("tkinter")
    pytest.importorskip("PIL")
    mod = importlib.import_module("casino.tk.cards")
    assert hasattr(mod, "tkCard") and hasattr(mod, "tkHand") and hasattr(mod, "tkTable")


def test_card_art_root_is_required_and_named(monkeypatch):
    from casino.tk import CARD_ART_ENV, card_art_root

    monkeypatch.delenv(CARD_ART_ENV, raising=False)
    with pytest.raises(RuntimeError, match=CARD_ART_ENV):
        card_art_root()


def test_card_art_root_must_be_a_directory(monkeypatch, tmp_path):
    from casino.tk import CARD_ART_ENV, card_art_root

    monkeypatch.setenv(CARD_ART_ENV, str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="not a directory"):
        card_art_root()


def test_card_art_root_returns_the_configured_directory(monkeypatch, tmp_path):
    from casino.tk import CARD_ART_ENV, card_art_root

    monkeypatch.setenv(CARD_ART_ENV, str(tmp_path))
    assert card_art_root() == str(tmp_path)
