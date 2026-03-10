from typing import Generator

import pytest
import taskiq_fastapi
from fastapi.testclient import TestClient

from app.main import app
from app.broker import broker


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