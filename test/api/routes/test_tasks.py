from fastapi.testclient import TestClient
from fastapi import status
import pytest


@pytest.fixture()
def task_mock(mocker):
    mock_task = mocker.MagicMock()
    mock_task.task_id = "test1234"
    return mock_task


@pytest.fixture()
def get_task_mock(mocker, task_mock):
    mocker.patch(
        "app.api.routes.tasks.download.download_reel.kiq",
        return_value=task_mock,
    )


def test_tasks_ok(get_task_mock, client: TestClient):
    data = {"uri": "https://www.instagram.com/reel/shortcode/"}
    response = client.post("/tasks", json=data)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json() == {"task_id": "test1234"}


def test_tasks_bad_url(client: TestClient):
    data = {"uri": "https://www.test.com/reel/shortcode/"}
    response = client.post("/tasks", json=data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"message": "Invalid URI. Only Instagram URLs are allowed."}


def test_tasks_bad_format(client: TestClient):
    data = {"uri": "https://www.instagram.com/test/"}
    response = client.post("/tasks", json=data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"message": "Invalid URI. The path is not valid for an Instagram reel."}