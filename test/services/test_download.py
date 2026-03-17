import uuid

import pytest
import sqlmodel
from sqlmodel import select
from taskiq import TaskiqMessage, TaskiqResult

from app.middlewares import ErrorHandlerMiddleware
from app.models import File, Task, TaskError, TaskStatus
from app.services import download


@pytest.fixture()
def task_in_db(db_session: sqlmodel.Session) -> Task:
    pending_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "pending")).one()

    task = Task(short_code="shortcode", status_code=pending_status.id, user_id=uuid.uuid4())
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture()
def post_mock(mocker):
    mock_post = mocker.MagicMock()
    mock_post.shortcode = "shortcode"
    return mock_post


@pytest.fixture()
def get_post_mock_ok(mocker, post_mock):
    mocker.patch(
        "app.services.download.instaloader.structures.Post.from_shortcode",
        return_value=post_mock,
    )


@pytest.fixture()
def get_post_mock_not_found(mocker):
    mocker.patch(
        "app.services.download.instaloader.structures.Post.from_shortcode",
        side_effect=Exception("Post not found"),
    )


@pytest.fixture()
def loader_mock(mocker):
    mock_loader = mocker.MagicMock()
    mocker.patch("app.services.download._get_instaloader", return_value=mock_loader)
    return mock_loader


@pytest.fixture()
def download_post_mock_ok(loader_mock):
    loader_mock.download_post.return_value = True


@pytest.fixture()
def download_post_mock_connection_error(loader_mock):
    loader_mock.download_post.side_effect = Exception("Connection error")


@pytest.fixture()
def download_post_mock_failed(loader_mock):
    loader_mock.download_post.return_value = False


@pytest.fixture()
def extract_audio_kiq_mock(mocker):
    return mocker.patch(
        "app.services.download.extract_audio.kiq",
        new_callable=mocker.AsyncMock,
    )


@pytest.mark.anyio
async def test_download_reel_ok(get_post_mock_ok, download_post_mock_ok, extract_audio_kiq_mock, task_in_db, db_session):
    task_dir = download.media_dir / str(task_in_db.id)
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "shortcode.mp4").write_bytes(b"fake video")

    result = await download.download_reel(task_id=str(task_in_db.id), session=db_session)
    assert result == "Instagram reel downloaded successfully."

    db_session.refresh(task_in_db)
    assert task_in_db.video_id is not None

    extract_audio_kiq_mock.assert_called_once_with(task_id=str(task_in_db.id))


@pytest.mark.anyio
async def test_download_reel_post_not_found(get_post_mock_not_found, task_in_db, db_session):
    with pytest.raises(Exception, match="Post not found"):
        await download.download_reel(task_id=str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_download_reel_connection_error(get_post_mock_ok, download_post_mock_connection_error, task_in_db, db_session):
    with pytest.raises(Exception, match="Connection error"):
        await download.download_reel(task_id=str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_download_reel_failed(get_post_mock_ok, download_post_mock_failed, task_in_db, db_session):
    with pytest.raises(RuntimeError, match="Failed to download"):
        await download.download_reel(task_id=str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_error_middleware_creates_task_error(task_in_db, db_session):
    message = TaskiqMessage(
        task_id="test-task-id",
        task_name="app.services.download:download_reel",
        labels={"step": "download"},
        args=[],
        kwargs={"short_code": "shortcode", "task_id": str(task_in_db.id)},
    )
    result = TaskiqResult(is_err=True, return_value=None, execution_time=0.1, labels={})
    exception = RuntimeError("Something went wrong")

    middleware = ErrorHandlerMiddleware()
    await middleware.on_error(message, result, exception)

    db_session.expire_all()

    task_error = db_session.exec(
        select(TaskError).where(TaskError.task_id == task_in_db.id)
    ).one()
    assert task_error.message == "Something went wrong"

    db_session.refresh(task_in_db)
    failed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "failed")).one()
    assert task_in_db.status_code == failed_status.id
