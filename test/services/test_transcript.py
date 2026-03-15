import uuid
from unittest.mock import MagicMock

import openai
import pytest
import sqlmodel
from sqlmodel import select

from app.models import AudioTrack, Download, Task, TaskError, TaskStatus, Transcript
from app.services import transcript


@pytest.fixture()
def task_in_db(db_session: sqlmodel.Session) -> Task:
    pending_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "pending")).one()

    task = Task(url="https://www.instagram.com/reel/transcript_shortcode/", status_code=pending_status.id)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture()
def audio_track_in_db(db_session: sqlmodel.Session, task_in_db: Task, tmp_path) -> AudioTrack:
    db_download = Download(shortcode="transcript_shortcode", file_path=str(tmp_path))
    db_session.add(db_download)
    db_session.commit()
    db_session.refresh(db_download)

    audio_path = tmp_path / "audio.mp3"
    db_audio_track = AudioTrack(
        download_id=db_download.id,
        file_path=str(audio_path),
        duration=42.0,
    )
    db_session.add(db_audio_track)
    task_in_db.download_id = db_download.id
    db_session.commit()
    db_session.refresh(db_audio_track)
    return db_audio_track


@pytest.fixture()
def audio_file(audio_track_in_db, tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake audio content")
    return audio


@pytest.fixture()
def whisper_mock_error(mocker, audio_file):
    return mocker.patch(
        "app.services.transcript.client.audio.transcriptions.create",
        side_effect=openai.RateLimitError(
            message="You exceeded your current quota",
            response=mocker.MagicMock(status_code=429),
            body={"message": "You exceeded your current quota", "type": "insufficient_quota", "param": None, "code": "insufficient_quota"},
        ),
    )


@pytest.fixture()
def topics_mock(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices[0].message.parsed = transcript.Topics(topics=["cooking", "italy", "pasta"])
    return mocker.patch(
        "app.services.transcript.client.chat.completions.parse",
        new_callable=mocker.AsyncMock,
        return_value=mock_response,
    )


@pytest.fixture()
def whisper_mock(mocker, audio_file, topics_mock):
    mock_response = mocker.MagicMock()
    mock_response.text = "Hello, this is a transcript."
    mock_response.language = "en"
    return mocker.patch(
        "app.services.transcript.client.audio.transcriptions.create",
        new_callable=mocker.AsyncMock,
        return_value=mock_response,
    )


@pytest.mark.anyio
async def test_transcribe_audio_ok(whisper_mock, audio_track_in_db, task_in_db, db_session, tmp_path):
    result = await transcript.transcribe_audio(str(audio_track_in_db.id), str(task_in_db.id), session=db_session)
    assert result == "Audio transcribed successfully."

    db_transcript = db_session.exec(
        select(Transcript).where(Transcript.audio_track_id == audio_track_in_db.id)
    ).one()
    assert db_transcript.language == "en"

    transcript_file = tmp_path / "audio.txt"
    assert transcript_file.exists()
    assert transcript_file.read_text(encoding="utf-8") == "Hello, this is a transcript."
    assert db_transcript.file_path == str(transcript_file)

    assert db_transcript.topics == "cooking, italy, pasta"

    db_session.refresh(task_in_db)
    completed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "completed")).one()
    assert task_in_db.status_code == completed_status.id


@pytest.mark.anyio
async def test_transcribe_audio_track_not_found(task_in_db, db_session):
    with pytest.raises(RuntimeError, match="not found"):
        await transcript.transcribe_audio(str(uuid.uuid4()), str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_transcribe_audio_api_error(whisper_mock_error, audio_track_in_db, task_in_db, db_session):
    with pytest.raises(RuntimeError, match="You exceeded your current quota"):
        await transcript.transcribe_audio(str(audio_track_in_db.id), str(task_in_db.id), session=db_session)


@pytest.mark.anyio
async def test_error_middleware_transcript_step(whisper_mock_error, audio_track_in_db, task_in_db, db_session):
    await transcript.transcribe_audio.kiq(audio_track_id=str(audio_track_in_db.id), task_id=str(task_in_db.id))

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
    mocker.patch(
        "app.services.transcript.client.chat.completions.parse",
        new_callable=mocker.AsyncMock,
        return_value=mock_response,
    )
    result = await transcript.extract_topics_llm("Some transcription text")
    assert result == "cooking, italy, pasta"


@pytest.mark.anyio
async def test_extract_topics_llm_empty_list(mocker):
    mock_response = MagicMock()
    mock_response.choices[0].message.parsed = transcript.Topics(topics=[])
    mocker.patch(
        "app.services.transcript.client.chat.completions.parse",
        new_callable=mocker.AsyncMock,
        return_value=mock_response,
    )
    result = await transcript.extract_topics_llm("Some transcription text")
    assert result is None


@pytest.mark.anyio
async def test_extract_topics_llm_parse_failure(mocker):
    mock_response = MagicMock()
    mock_response.choices[0].message.parsed = None
    mocker.patch(
        "app.services.transcript.client.chat.completions.parse",
        new_callable=mocker.AsyncMock,
        return_value=mock_response,
    )
    result = await transcript.extract_topics_llm("Some transcription text")
    assert result is None


@pytest.mark.anyio
async def test_extract_topics_llm_api_error(mocker):
    mocker.patch(
        "app.services.transcript.client.chat.completions.parse",
        side_effect=openai.RateLimitError(
            message="You exceeded your current quota",
            response=mocker.MagicMock(status_code=429),
            body={"message": "You exceeded your current quota"},
        ),
    )
    result = await transcript.extract_topics_llm("Some transcription text")
    assert result is None


@pytest.mark.anyio
async def test_transcribe_audio_topics_failure_still_completes(
    whisper_mock, audio_track_in_db, task_in_db, db_session, mocker
):
    """transcribe_audio completes successfully even when topics extraction fails."""
    mocker.patch(
        "app.services.transcript.client.chat.completions.parse",
        side_effect=openai.RateLimitError(
            message="You exceeded your current quota",
            response=mocker.MagicMock(status_code=429),
            body={"message": "You exceeded your current quota"},
        ),
    )
    result = await transcript.transcribe_audio(str(audio_track_in_db.id), str(task_in_db.id), session=db_session)
    assert result == "Audio transcribed successfully."

    db_transcript = db_session.exec(
        select(Transcript).where(Transcript.audio_track_id == audio_track_in_db.id)
    ).one()
    assert db_transcript.topics is None

    db_session.refresh(task_in_db)
    completed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "completed")).one()
    assert task_in_db.status_code == completed_status.id
