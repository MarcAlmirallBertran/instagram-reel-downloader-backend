import uuid

import pytest
import sqlmodel
from sqlmodel import select
from taskiq import TaskiqMessage, TaskiqResult

from app.middlewares import ErrorHandlerMiddleware
from app.models import AudioTrack, Download, Task, TaskError, TaskStatus
from app.services import audio


@pytest.fixture()
def task_in_db(db_session: sqlmodel.Session) -> Task:
    pending_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "pending")).one()

    task = Task(url="https://www.instagram.com/reel/shortcode/", status_code=pending_status.id)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture()
def download_in_db(db_session: sqlmodel.Session, task_in_db: Task, tmp_path) -> Download:
    db_download = Download(shortcode="audio_shortcode", file_path=str(tmp_path))
    db_session.add(db_download)
    task_in_db.download_id = db_download.id
    db_session.commit()
    db_session.refresh(db_download)
    return db_download


@pytest.fixture()
def video_file(tmp_path, download_in_db):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video content")
    return video


@pytest.fixture()
def audio_segment_mock(mocker, video_file):
    mock_segment = mocker.MagicMock()
    mock_segment.duration_seconds = 42.0
    mocker.patch("app.services.audio.pydub.AudioSegment.from_file", return_value=mock_segment)
    return mock_segment


@pytest.fixture()
def transcribe_audio_kiq_mock(mocker):
    return mocker.patch(
        "app.services.audio.transcribe_audio.kiq",
        new_callable=mocker.AsyncMock,
    )


@pytest.mark.anyio
async def test_extract_audio_ok(audio_segment_mock, transcribe_audio_kiq_mock, download_in_db, task_in_db, db_session):
    result = await audio.extract_audio(str(download_in_db.id), str(task_in_db.id), session=db_session)
    assert result == "Audio extracted successfully."

    db_audio = db_session.exec(
        select(AudioTrack).where(AudioTrack.download_id == download_in_db.id)
    ).one()
    assert db_audio is not None
    assert db_audio.duration == 42.0
    assert db_audio.file_path.endswith(".mp3")

    transcribe_audio_kiq_mock.assert_called_once_with(audio_track_id=str(db_audio.id), task_id=str(task_in_db.id))


@pytest.mark.anyio
async def test_extract_audio_download_not_found(task_in_db, db_session):
    with pytest.raises(RuntimeError, match="not found"):
        await audio.extract_audio(str(uuid.uuid4()), str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_extract_audio_no_video_file(download_in_db, task_in_db, db_session):
    with pytest.raises(RuntimeError, match="No video file found"):
        await audio.extract_audio(str(download_in_db.id), str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_extract_audio_conversion_error(video_file, download_in_db, task_in_db, db_session, mocker):
    mocker.patch(
        "app.services.audio.pydub.AudioSegment.from_file",
        side_effect=Exception("Conversion error"),
    )
    with pytest.raises(Exception, match="Conversion error"):
        await audio.extract_audio(str(download_in_db.id), str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_error_middleware_audio_step(task_in_db, db_session):
    message = TaskiqMessage(
        task_id="test-task-id",
        task_name="app.services.audio:extract_audio",
        labels={"step": "audio"},
        args=[],
        kwargs={"download_id": str(uuid.uuid4()), "task_id": str(task_in_db.id)},
    )
    result = TaskiqResult(is_err=True, return_value=None, execution_time=0.1, labels={})
    exception = RuntimeError("Audio conversion failed")

    middleware = ErrorHandlerMiddleware()
    await middleware.on_error(message, result, exception)

    db_session.expire_all()

    task_error = db_session.exec(
        select(TaskError).where(TaskError.task_id == task_in_db.id)
    ).one()
    assert task_error.message == "Audio conversion failed"

    db_session.refresh(task_in_db)
    failed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "failed")).one()
    assert task_in_db.status_code == failed_status.id
