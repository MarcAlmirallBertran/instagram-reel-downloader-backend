import uuid

import sqlmodel
from fastapi.testclient import TestClient
from fastapi import status
import pytest
from sqlmodel import select

from app.models import Task, TaskStatus


@pytest.fixture()
def get_task_mock(mocker):
    mocker.patch(
        "app.api.routes.tasks.download.download_reel.kiq",
        return_value=mocker.AsyncMock(),
    )


def test_tasks_ok(get_task_mock, client: TestClient):
    data = {"uri": "https://www.instagram.com/reel/shortcode/"}
    response = client.post("/tasks", json=data)
    assert response.status_code == status.HTTP_201_CREATED
    task_id = response.json()["task_id"]
    uuid.UUID(task_id)


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


# --- cancel endpoint ---

def test_cancel_task_ok(get_task_mock, client: TestClient, db_session: sqlmodel.Session):
    response = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/cancel_ok_shortcode/"})
    assert response.status_code == status.HTTP_201_CREATED
    task_id = response.json()["task_id"]

    response = client.post(f"/tasks/{task_id}/cancel")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "Task cancelled successfully."}

    task = db_session.get(Task, uuid.UUID(task_id))
    assert task is not None
    db_session.refresh(task)
    assert task.cancelled is True


def test_cancel_task_not_found(client: TestClient):
    response = client.post(f"/tasks/{uuid.uuid4()}/cancel")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"message": "Task not found."}


def test_cancel_task_already_completed(get_task_mock, client: TestClient, db_session: sqlmodel.Session):
    response = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/cancel_completed_shortcode/"})
    task_id = response.json()["task_id"]

    completed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "completed")).one()
    task = db_session.get(Task, uuid.UUID(task_id))
    assert task is not None
    task.status_code = completed_status.id
    db_session.commit()

    response = client.post(f"/tasks/{task_id}/cancel")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "completed" in response.json()["message"]


def test_cancel_task_already_cancelled(get_task_mock, client: TestClient, db_session: sqlmodel.Session):
    response = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/cancel_already_shortcode/"})
    task_id = response.json()["task_id"]

    cancelled_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "cancelled")).one()
    task = db_session.get(Task, uuid.UUID(task_id))
    assert task is not None
    task.status_code = cancelled_status.id
    db_session.commit()

    response = client.post(f"/tasks/{task_id}/cancel")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "cancelled" in response.json()["message"]