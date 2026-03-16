import io
import uuid
import zipfile
from datetime import datetime

import sqlmodel
from fastapi.testclient import TestClient
from fastapi import status
import pytest
from sqlmodel import select

from app.models import Download, Task, TaskError, TaskStatus, TaskStep


@pytest.fixture()
def get_task_mock(mocker):
    mocker.patch(
        "app.api.routes.tasks.download.download_reel.kiq",
        return_value=mocker.AsyncMock(),
    )


def test_list_tasks_ok(get_task_mock, client: TestClient, auth_headers: dict):
    client.post("/tasks", json={"uri": "https://www.instagram.com/reel/list_shortcode/"}, headers=auth_headers)
    response = client.get("/tasks", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) >= 1
    task = next(t for t in tasks if t["url"] == "https://www.instagram.com/reel/list_shortcode/")
    assert task["status"] == "pending"
    assert task["cancelled"] is False
    assert "id" in task
    assert "created_at" in task
    assert "updated_at" in task


def test_get_task_ok(get_task_mock, client: TestClient, auth_headers: dict):
    resp = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/detail_shortcode/"}, headers=auth_headers)
    task_id = resp.json()["task_id"]

    response = client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == task_id
    assert data["status"] == "pending"
    assert data["cancelled"] is False
    assert data["download"] is None
    assert data["audio"] is None
    assert data["transcript"] is None


def test_get_task_not_found(client: TestClient, auth_headers: dict):
    response = client.get(f"/tasks/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- media endpoints (no download yet → 404) ---

def test_get_video_not_ready(get_task_mock, client: TestClient, auth_headers: dict):
    resp = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/video_sc/"}, headers=auth_headers)
    task_id = resp.json()["task_id"]
    response = client.get(f"/tasks/{task_id}/video", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_audio_not_ready(get_task_mock, client: TestClient, auth_headers: dict):
    resp = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/audio_sc/"}, headers=auth_headers)
    task_id = resp.json()["task_id"]
    response = client.get(f"/tasks/{task_id}/audio", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_transcript_not_ready(get_task_mock, client: TestClient, auth_headers: dict):
    resp = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/transcript_sc/"}, headers=auth_headers)
    task_id = resp.json()["task_id"]
    response = client.get(f"/tasks/{task_id}/transcript", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_video_task_not_found(client: TestClient, auth_headers: dict):
    response = client.get(f"/tasks/{uuid.uuid4()}/video", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_tasks_unauthenticated(client: TestClient):
    response = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/shortcode/"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_tasks_ok(get_task_mock, client: TestClient, auth_headers: dict):
    data = {"uri": "https://www.instagram.com/reel/shortcode/"}
    response = client.post("/tasks", json=data, headers=auth_headers)
    assert response.status_code == status.HTTP_201_CREATED
    task_id = response.json()["task_id"]
    uuid.UUID(task_id)


def test_tasks_bad_url(client: TestClient, auth_headers: dict):
    data = {"uri": "https://www.test.com/reel/shortcode/"}
    response = client.post("/tasks", json=data, headers=auth_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"message": "Invalid URI. Only Instagram URLs are allowed."}


def test_tasks_bad_format(client: TestClient, auth_headers: dict):
    data = {"uri": "https://www.instagram.com/test/"}
    response = client.post("/tasks", json=data, headers=auth_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"message": "Invalid URI. The path is not valid for an Instagram reel."}


# --- cancel endpoint ---

def test_cancel_task_ok(get_task_mock, client: TestClient, auth_headers: dict, db_session: sqlmodel.Session):
    response = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/cancel_ok_shortcode/"}, headers=auth_headers)
    assert response.status_code == status.HTTP_201_CREATED
    task_id = response.json()["task_id"]

    response = client.post(f"/tasks/{task_id}/cancel", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "Task cancelled successfully."}

    task = db_session.get(Task, uuid.UUID(task_id))
    assert task is not None
    db_session.refresh(task)
    assert task.cancelled is True


def test_cancel_task_not_found(client: TestClient, auth_headers: dict):
    response = client.post(f"/tasks/{uuid.uuid4()}/cancel", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"message": "Task not found."}


def test_cancel_task_already_completed(get_task_mock, client: TestClient, auth_headers: dict, db_session: sqlmodel.Session):
    response = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/cancel_completed_shortcode/"}, headers=auth_headers)
    task_id = response.json()["task_id"]

    completed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "completed")).one()
    task = db_session.get(Task, uuid.UUID(task_id))
    assert task is not None
    task.status_code = completed_status.id
    db_session.commit()

    response = client.post(f"/tasks/{task_id}/cancel", headers=auth_headers)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "completed" in response.json()["message"]


def test_cancel_task_already_cancelled(get_task_mock, client: TestClient, auth_headers: dict, db_session: sqlmodel.Session):
    response = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/cancel_already_shortcode/"}, headers=auth_headers)
    task_id = response.json()["task_id"]

    cancelled_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "cancelled")).one()
    task = db_session.get(Task, uuid.UUID(task_id))
    assert task is not None
    task.status_code = cancelled_status.id
    db_session.commit()

    response = client.post(f"/tasks/{task_id}/cancel", headers=auth_headers)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "cancelled" in response.json()["message"]


def test_list_tasks_includes_errors(get_task_mock, client: TestClient, auth_headers: dict, db_session: sqlmodel.Session):
    resp = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/list_errors_sc/"}, headers=auth_headers)
    task_id = uuid.UUID(resp.json()["task_id"])

    step = db_session.exec(select(TaskStep).where(TaskStep.code == "download")).one()
    db_session.add(TaskError(task_id=task_id, step_code=step.id, message="download failed"))
    db_session.commit()

    response = client.get("/tasks", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    task = next(t for t in tasks if t["id"] == str(task_id))
    assert len(task["errors"]) == 1
    assert task["errors"][0]["step"] == "download"
    assert task["errors"][0]["message"] == "download failed"
    assert task["errors"][0]["detail"] is None


def test_get_task_includes_errors(get_task_mock, client: TestClient, auth_headers: dict, db_session: sqlmodel.Session):
    resp = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/detail_errors_sc/"}, headers=auth_headers)
    task_id = uuid.UUID(resp.json()["task_id"])

    step = db_session.exec(select(TaskStep).where(TaskStep.code == "audio")).one()
    db_session.add(TaskError(task_id=task_id, step_code=step.id, message="audio failed", detail="ffmpeg error"))
    db_session.commit()

    response = client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["errors"]) == 1
    assert data["errors"][0]["step"] == "audio"
    assert data["errors"][0]["message"] == "audio failed"
    assert data["errors"][0]["detail"] == "ffmpeg error"


# --- list_tasks filtering and sorting ---

def test_list_tasks_filter_by_status(get_task_mock, client: TestClient, auth_headers: dict, db_session: sqlmodel.Session):
    resp = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/filter_pending_sc/"}, headers=auth_headers)
    pending_id = resp.json()["task_id"]

    resp2 = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/filter_completed_sc/"}, headers=auth_headers)
    completed_id = resp2.json()["task_id"]

    completed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "completed")).one()
    task = db_session.get(Task, uuid.UUID(completed_id))
    assert task is not None
    task.status_code = completed_status.id
    db_session.commit()

    response = client.get("/tasks?status=pending", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    ids = [t["id"] for t in response.json()]
    assert pending_id in ids
    assert completed_id not in ids


def test_list_tasks_filter_invalid_status(client: TestClient, auth_headers: dict):
    response = client.get("/tasks?status=not_a_real_status", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_list_tasks_sort_order_asc(get_task_mock, client: TestClient, auth_headers: dict, db_session: sqlmodel.Session):
    resp1 = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/sort_asc_sc1/"}, headers=auth_headers)
    resp2 = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/sort_asc_sc2/"}, headers=auth_headers)
    id1, id2 = resp1.json()["task_id"], resp2.json()["task_id"]

    task1 = db_session.get(Task, uuid.UUID(id1))
    task2 = db_session.get(Task, uuid.UUID(id2))
    task1.created_at = datetime(2020, 1, 1)
    task2.created_at = datetime(2020, 1, 2)
    db_session.commit()

    response = client.get("/tasks?sort_by=created_at&sort_order=asc", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    ids = [t["id"] for t in tasks]
    assert ids.index(id1) < ids.index(id2)


def test_list_tasks_sort_order_desc(get_task_mock, client: TestClient, auth_headers: dict, db_session: sqlmodel.Session):
    resp1 = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/sort_desc_sc1/"}, headers=auth_headers)
    resp2 = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/sort_desc_sc2/"}, headers=auth_headers)
    id1, id2 = resp1.json()["task_id"], resp2.json()["task_id"]

    task1 = db_session.get(Task, uuid.UUID(id1))
    task2 = db_session.get(Task, uuid.UUID(id2))
    task1.created_at = datetime(2020, 1, 1)
    task2.created_at = datetime(2020, 1, 2)
    db_session.commit()

    response = client.get("/tasks?sort_by=created_at&sort_order=desc", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    ids = [t["id"] for t in tasks]
    assert ids.index(id2) < ids.index(id1)


# --- files (zip) endpoint ---

def test_get_files_not_ready(get_task_mock, client: TestClient, auth_headers: dict):
    resp = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/files_notready_sc/"}, headers=auth_headers)
    task_id = resp.json()["task_id"]
    response = client.get(f"/tasks/{task_id}/files", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_files_task_not_found(client: TestClient, auth_headers: dict):
    response = client.get(f"/tasks/{uuid.uuid4()}/files", headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_files_ok(get_task_mock, client: TestClient, auth_headers: dict, db_session: sqlmodel.Session, tmp_path):
    resp = client.post("/tasks", json={"uri": "https://www.instagram.com/reel/files_ok_sc/"}, headers=auth_headers)
    task_id = uuid.UUID(resp.json()["task_id"])

    # create fake files in a temp directory
    task_dir = tmp_path / str(task_id)
    task_dir.mkdir()
    (task_dir / "files_ok_sc.mp4").write_bytes(b"fake video")
    (task_dir / "files_ok_sc.mp3").write_bytes(b"fake audio")
    (task_dir / "files_ok_sc.txt").write_text("fake transcript")

    db_download = Download(shortcode="files_ok_sc", file_path=str(task_dir), task_id=task_id)
    db_session.add(db_download)
    db_session.commit()
    db_session.refresh(db_download)

    task = db_session.get(Task, task_id)
    assert task is not None
    task.download_id = db_download.id
    db_session.commit()

    response = client.get(f"/tasks/{task_id}/files", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/zip"
    assert f"{task_id}.zip" in response.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(response.content))
    names = zf.namelist()
    assert "files_ok_sc.mp4" in names
    assert "files_ok_sc.mp3" in names
    assert "files_ok_sc.txt" in names
