from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import creator_store as store
from app.creator import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("RESOLVE_CREATOR_DB", str(tmp_path / "creator.sqlite3"))
    for name in (
        "STRIPE_SECRET_KEY",
        "STRIPE_PRICE_ID",
        "STRIPE_WEBHOOK_SECRET",
        "RESOLVE_PUBLIC_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(store, "today", lambda: date(2026, 9, 30))
    with TestClient(app) as instance:
        yield instance
