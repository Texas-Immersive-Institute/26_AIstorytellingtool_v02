from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "lighthouse"


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AISTORY_DATA_DIR", str(tmp_path / "appdata"))


async def no_ai():
    """Stand-in for choose_backend: tests never call real CLIs or local models."""
    return None, "AI is off in tests."
