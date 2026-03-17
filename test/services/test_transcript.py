import mimetypes
import pathlib
import uuid
from unittest.mock import MagicMock

import openai
import pytest
import sqlmodel
from sqlmodel import select

from app.models import File, Task, TaskError, TaskStatus
from app.services import transcript


@pytest.fixture()
def task_in_db(db_session: sqlmodel.Session) -> Task:
    pending_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "pending")).one()

    task = Task(short_code="transcript_shortcode", status_code=pending_status.id, user_id=uuid.uuid4())
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture()
def audio_track_in_db(db_session: sqlmodel.Session, task_in_db: Task, tmp_path) -> File:

    audio_path = tmp_path / "audio.mp3"
    db_audio_track = File(
        path=str(audio_path),
        mime_type="audio/mpeg",
    )
    db_session.add(db_audio_track)
    task_in_db.audio_id = db_audio_track.id
    db_session.commit()
    return db_audio_track


@pytest.fixture()
def audio_file(audio_track_in_db):
    audio = pathlib.Path(audio_track_in_db.path)
    audio.write_bytes(b"fake audio content")
    return audio


@pytest.fixture()
def openai_client_mock(mocker):
    mock_client = mocker.MagicMock()
    mocker.patch("app.services.transcript._get_openai_client", return_value=mock_client)
    return mock_client


@pytest.fixture()
def whisper_mock_error(mocker, openai_client_mock, audio_file):
    openai_client_mock.audio.transcriptions.create = mocker.AsyncMock(
        side_effect=openai.RateLimitError(
            message="You exceeded your current quota",
            response=mocker.MagicMock(status_code=429),
            body={"message": "You exceeded your current quota", "type": "insufficient_quota", "param": None, "code": "insufficient_quota"},
        )
    )
    return openai_client_mock


@pytest.fixture()
def topics_mock(mocker, openai_client_mock):
    mock_response = mocker.MagicMock()
    mock_response.choices[0].message.parsed = transcript.Topics(topics=["cooking", "italy", "pasta"])
    openai_client_mock.chat.completions.parse = mocker.AsyncMock(return_value=mock_response)
    return openai_client_mock


@pytest.fixture()
def whisper_mock(mocker, openai_client_mock, audio_file, topics_mock):
    mock_response = mocker.MagicMock()
    mock_response.text = "Hello, this is a transcript."
    mock_response.language = "en"
    openai_client_mock.audio.transcriptions.create = mocker.AsyncMock(return_value=mock_response)
    return openai_client_mock


@pytest.mark.anyio
async def test_transcribe_audio_ok(whisper_mock, audio_track_in_db, task_in_db, db_session, tmp_path):
    result = await transcript.transcribe_audio(task_id=str(task_in_db.id), session=db_session)
    assert result == "Audio transcribed successfully."

    db_session.refresh(task_in_db)
    assert task_in_db.language == "en"
    assert task_in_db.topics == "cooking, italy, pasta"

    transcript_file = tmp_path / "audio.txt"
    assert transcript_file.exists()
    assert transcript_file.read_text(encoding="utf-8") == "Hello, this is a transcript."

    db_transcript = db_session.exec(select(File).where(File.id == task_in_db.transcript_id)).one()
    assert db_transcript.path == str(transcript_file)

    completed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "completed")).one()
    assert task_in_db.status_code == completed_status.id


@pytest.mark.anyio
async def test_transcribe_audio_track_not_found(task_in_db, db_session):
    with pytest.raises(Exception):
        await transcript.transcribe_audio(task_id=str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_transcribe_audio_api_error(whisper_mock_error, audio_track_in_db, task_in_db, db_session):
    with pytest.raises(RuntimeError, match="You exceeded your current quota"):
        await transcript.transcribe_audio(task_id=str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_error_middleware_transcript_step(whisper_mock_error, audio_track_in_db, task_in_db, db_session):
    await transcript.transcribe_audio.kiq(task_id=str(task_in_db.id))

    db_session.expire_all()

    task_error = db_session.exec(
        select(TaskError).where(TaskError.task_id == task_in_db.id)
    ).one()
    assert task_error.message == "You exceeded your current quota"

    db_session.refresh(task_in_db)
    failed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "failed")).one()
    assert task_in_db.status_code == failed_status.id


# --- extract_topics_llm unit tests ---

@pytest.mark.anyio
async def test_extract_topics_llm_ok(mocker):
    mock_response = MagicMock()
    mock_response.choices[0].message.parsed = transcript.Topics(topics=["cooking", " italy ", "pasta"])
    mock_client = mocker.MagicMock()
    mock_client.chat.completions.parse = mocker.AsyncMock(return_value=mock_response)
    result = await transcript.extract_topics_llm("Some transcription text", mock_client)
    assert result == "cooking, italy, pasta"


@pytest.mark.anyio
async def test_extract_topics_llm_empty_list(mocker):
    mock_response = MagicMock()
    mock_response.choices[0].message.parsed = transcript.Topics(topics=[])
    mock_client = mocker.MagicMock()
    mock_client.chat.completions.parse = mocker.AsyncMock(return_value=mock_response)
    result = await transcript.extract_topics_llm("Some transcription text", mock_client)
    assert result is None


@pytest.mark.anyio
async def test_extract_topics_llm_parse_failure(mocker):
    mock_response = MagicMock()
    mock_response.choices[0].message.parsed = None
    mock_client = mocker.MagicMock()
    mock_client.chat.completions.parse = mocker.AsyncMock(return_value=mock_response)
    result = await transcript.extract_topics_llm("Some transcription text", mock_client)
    assert result is None


@pytest.mark.anyio
async def test_extract_topics_llm_api_error(mocker):
    mock_client = mocker.MagicMock()
    mock_client.chat.completions.parse = mocker.AsyncMock(
        side_effect=openai.RateLimitError(
            message="You exceeded your current quota",
            response=mocker.MagicMock(status_code=429),
            body={"message": "You exceeded your current quota"},
        )
    )
    result = await transcript.extract_topics_llm("Some transcription text", mock_client)
    assert result is None


@pytest.mark.anyio
async def test_transcribe_audio_topics_failure_still_completes(
    whisper_mock, audio_track_in_db, task_in_db, db_session, mocker
):
    """transcribe_audio completes successfully even when topics extraction fails."""
    whisper_mock.chat.completions.parse = mocker.AsyncMock(
        side_effect=openai.RateLimitError(
            message="You exceeded your current quota",
            response=mocker.MagicMock(status_code=429),
            body={"message": "You exceeded your current quota"},
        )
    )
    result = await transcript.transcribe_audio(task_id=str(task_in_db.id), session=db_session)
    assert result == "Audio transcribed successfully."

    db_session.refresh(task_in_db)
    assert task_in_db.topics is None
    completed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "completed")).one()
    assert task_in_db.status_code == completed_status.id
