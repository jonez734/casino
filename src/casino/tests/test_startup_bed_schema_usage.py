"""casino startup grants schema usage to the bed role.

bed connects as the bed role and runs casino's table checks, so it needs usage on
the casino schema, as web, term, sysop, and zoid6 already have.
"""

import re
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "startup" / "main.py"


def test_bed_role_granted_schema_usage():
    text = MAIN.read_text(encoding="utf-8")
    m = re.search(r"for role in \(([^)]*)\):", text)
    assert m, "casino schema usage loop not found"
    roles = [r.strip().strip('"\'') for r in m.group(1).split(",") if r.strip()]
    assert "bed" in roles, f"usage not granted to bed; granted to {roles}"
