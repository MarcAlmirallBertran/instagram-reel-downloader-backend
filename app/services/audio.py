import logging
import mimetypes
import pathlib
import uuid

import pydub
import sqlmodel
from taskiq import TaskiqDepends

from app.broker import broker
from app.api.deps import get_db
from app.models import File, Task, TaskStatus
from app.services.transcript import transcribe_audio


logger = logging.getLogger(__name__)


@broker.task(step="audio")
async def extract_audio(
    task_id: str,
    session: sqlmodel.Session = TaskiqDepends(get_db),
):
    logger.info(f"Starting audio extraction for task {task_id}")
    
    task = session.exec(
        sqlmodel.select(Task).where(Task.id == uuid.UUID(task_id))
    ).one()
    
    if task.cancelled:
        return "Task was cancelled."
        
    processing_status = session.exec(
        sqlmodel.select(TaskStatus).where(TaskStatus.code == "processing")
    ).one()
        
    task.status_code = processing_status.id
    session.commit()
    
    db_video = session.exec(
        sqlmodel.select(File).where(File.id == task.video_id)
    ).one()

    video_path = pathlib.Path(db_video.path)
    video_format = video_path.suffix.lower()
    audio_path = video_path.with_suffix(".mp3")

    audio = pydub.AudioSegment.from_file(video_path, format=video_format[1:])
    audio.export(audio_path, format="mp3")
    
    mime_type, _ = mimetypes.guess_type(audio_path.name)
    if mime_type is None:
        raise RuntimeError(f"Could not determine MIME type for audio file {audio_path}")

    db_audio = File(path=str(audio_path), mime_type=mime_type)
    session.add(db_audio)
    task.audio_id = db_audio.id
    
    session.commit()

    await transcribe_audio.kiq(task_id=task_id)

    return "Audio extracted successfully."
