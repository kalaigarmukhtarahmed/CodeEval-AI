import atexit
import os
import tempfile
import pytest

_temp_dir = tempfile.TemporaryDirectory()
os.environ["CODEEVAL_DATA_DIR"] = _temp_dir.name
os.environ["MAX_UPLOAD_BYTES"] = "4096"
os.environ["MAX_UNCOMPRESSED_BYTES"] = "4096"

from fastapi.testclient import TestClient
from app.database import Base, SessionLocal, engine
from app.main import app


def _cleanup():
    try:
        engine.dispose()
    except Exception:
        pass
    try:
        _temp_dir.cleanup()
    except Exception:
        pass


atexit.register(_cleanup)


def pytest_sessionstart(session):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def pytest_sessionfinish(session, exitstatus):
    _cleanup()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
