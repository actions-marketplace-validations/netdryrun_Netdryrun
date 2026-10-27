"""Every file in the 0.3.0 false-pass advisory must stay refused: each one is a check that didn't test what it said."""
import subprocess
import sys
from pathlib import Path

import pytest

ADVISORY = Path(__file__).resolve().parents[1] / "advisories" / "0.3.0-false-pass"
FIXTURES = sorted(ADVISORY.glob("*.yml"))


def test_the_advisory_has_its_fixtures():
    assert len(FIXTURES) >= 7


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_validate_refuses_it(fixture):
    p = subprocess.run([sys.executable, "-m", "netdryrun", "validate", str(fixture)],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 2, p.stdout + p.stderr
    assert "config error" in (p.stdout + p.stderr)
