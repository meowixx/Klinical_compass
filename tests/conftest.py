"""Tests never open the operator's database or contact MAX."""
import os
import tempfile
from pathlib import Path

import pytest

_directory = tempfile.TemporaryDirectory(prefix="compass-tests-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_directory.name) / "tests.db")


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    from app.database import Base, engine
    import app.max_bot as bot

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    def no_network(*args, **kwargs):
        raise AssertionError("Tests must mock MAX transport")

    monkeypatch.setattr(bot, "max_api_request", no_network)
    yield



def pytest_sessionfinish(session, exitstatus):
    from app.database import engine
    engine.dispose()
    _directory.cleanup()
