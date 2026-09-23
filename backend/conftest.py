import json
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(settings.FIXTURES_DIR)


@pytest.fixture(scope="session")
def fixture_manifest(fixtures_dir: Path) -> dict[str, Any]:
    path = fixtures_dir / "generated" / "manifest.json"
    if not path.exists():
        pytest.fail("Fixtures not built. Run `make fixtures`.")
    data: dict[str, Any] = json.loads(path.read_text())
    return data
