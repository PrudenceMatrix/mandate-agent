import pytest

from app import db


@pytest.fixture(autouse=True)
def tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB", str(tmp_path / "ledger.db"))
    db.init()
