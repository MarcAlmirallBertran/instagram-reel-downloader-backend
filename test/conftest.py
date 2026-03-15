from collections.abc import Generator

import pytest
import sqlmodel
import taskiq_fastapi
from fastapi.testclient import TestClient

from app.main import app
from app.broker import broker
from app.core.db import engine


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def init_taskiq_deps():

    taskiq_fastapi.populate_dependency_context(broker, app)

    yield

    broker.custom_dependency_context = {}


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client: TestClient) -> dict[str, str]:
    client.post("/users", json={"username": "authtestuser", "password": "testpass123"})
    resp = client.post("/users/login", data={"username": "authtestuser", "password": "testpass123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def db_session() -> Generator[sqlmodel.Session, None, None]:
    with sqlmodel.Session(engine) as session:
        yield session
