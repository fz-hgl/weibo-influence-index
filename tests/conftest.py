import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wii.ingest import fixtures  # noqa: E402
from wii.store import load_cohort  # noqa: E402


@pytest.fixture(scope="session")
def demo_dir(tmp_path_factory):
    """Generate the synthetic demo cohort once per test session."""
    out = tmp_path_factory.mktemp("demo-data")
    fixtures.generate(out, seed=fixtures.SEED)
    return out


@pytest.fixture(scope="session")
def demo_cohort(demo_dir):
    cohort, tables = load_cohort(demo_dir)
    return cohort
