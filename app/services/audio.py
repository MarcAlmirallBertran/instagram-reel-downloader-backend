import logging
import pathlib
import uuid

import pydub
import sqlmodel
from taskiq import TaskiqDepends

from app.broker import broker
from app.api.deps import get_db
from app.models import AudioTrack, Download, Task, TaskStatus
from app.services.transcript import transcribe_audio


logger = logging.getLogger(__name__)


@broker.task(step="audio")
async def extract_audio(
    download_id: str,
    task_id: str,
    session: sqlmodel.Session = TaskiqDepends(get_db),
):
    logger.info(f"Starting audio extraction for task {task_id} with download ID {download_id}")
    processing_status = session.exec(
        sqlmodel.select(TaskStatus).where(TaskStatus.code == "processing")
    ).one()

    task = session.get(Task, uuid.UUID(task_id))
    if task and task.cancelled:
        return "Task was cancelled."
    if task:
        task.status_code = processing_status.id
        session.commit()

    db_download = session.get(Download, uuid.UUID(download_id))
    if not db_download:
        raise RuntimeError(f"Download {download_id} not found.")

    video_dir = pathlib.Path(db_download.file_path)
    video_files = list(video_dir.glob("*.mp4"))

    if not video_files:
        raise RuntimeError(f"No video file found in {video_dir}.")

    video_path = video_files[0]
    video_format = video_path.suffix.lower()
    audio_path = video_path.with_suffix(".mp3")

    audio = pydub.AudioSegment.from_file(video_path, format=video_format[1:])
    audio.export(audio_path, format="mp3")

    db_audio_track = AudioTrack(
        download_id=uuid.UUID(download_id),
        file_path=str(audio_path),
        duration=audio.duration_seconds,
    )
    session.add(db_audio_track)
    session.commit()

    await transcribe_audio.kiq(audio_track_id=str(db_audio_track.id), task_id=task_id)

    return "Audio extracted successfully."
