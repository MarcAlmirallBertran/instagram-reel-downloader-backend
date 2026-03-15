import logging
import pathlib
import uuid
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic.main import BaseModel

from sqlmodel import select

from app.api.deps import CurrentUserDep, SessionDep
from app.models import AudioTrack, Download, Task, TaskError, TaskStatus, TaskStep, Transcript
from app.services import download

logger = logging.getLogger(__name__)

VALID_PATH_PREFIXES = ("reel")
router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    task_id: str


class ErrorDetail(BaseModel):
    step: str
    message: str
    detail: str | None
    created_at: datetime


class TaskListItem(BaseModel):
    id: str
    url: str
    status: str
    cancelled: bool
    created_at: datetime
    updated_at: datetime
    errors: list[ErrorDetail]


class DownloadDetail(BaseModel):
    shortcode: str
    file_path: str


class AudioDetail(BaseModel):
    file_path: str
    duration: float | None


class TranscriptDetail(BaseModel):
    language: str | None
    topics: str | None
    file_path: str


class TaskDetail(BaseModel):
    id: str
    url: str
    status: str
    cancelled: bool
    created_at: datetime
    updated_at: datetime
    download: DownloadDetail | None
    audio: AudioDetail | None
    transcript: TranscriptDetail | None
    errors: list[ErrorDetail]


class Message(BaseModel):
    message: str


class TaskCreateRequest(BaseModel):
    uri: str


def _get_errors_for_task(task_id: uuid.UUID, session) -> list[ErrorDetail]:
    errors = session.exec(select(TaskError).where(TaskError.task_id == task_id)).all()
    steps = {s.id: s.code for s in session.exec(select(TaskStep)).all()}
    return [
        ErrorDetail(step=steps[e.step_code], message=e.message, detail=e.detail, created_at=e.created_at)
        for e in errors
    ]


@router.get("", status_code=status.HTTP_200_OK, response_model=list[TaskListItem])
async def list_tasks(session: SessionDep, current_user: CurrentUserDep):
    tasks = session.exec(select(Task).where(Task.user_id == current_user.id)).all()
    statuses = {s.id: s.code for s in session.exec(select(TaskStatus)).all()}
    return [
        TaskListItem(
            id=str(t.id),
            url=t.url,
            status=statuses[t.status_code],
            cancelled=t.cancelled,
            created_at=t.created_at,
            updated_at=t.updated_at,
            errors=_get_errors_for_task(t.id, session),
        )
        for t in tasks
    ]


@router.get(
    "/{task_id}",
    status_code=status.HTTP_200_OK,
    response_model=TaskDetail,
    responses={404: {"model": Message, "description": "Task not found."}},
)
async def get_task(task_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep):
    task = _get_task_for_user(task_id, current_user, session)
    if isinstance(task, JSONResponse):
        return task

    task_status = session.get(TaskStatus, task.status_code)
    if not task_status:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Task not found."})

    db_download = session.get(Download, task.download_id) if task.download_id else None
    db_audio = session.exec(select(AudioTrack).where(AudioTrack.download_id == db_download.id)).first() if db_download else None
    db_transcript = session.exec(select(Transcript).where(Transcript.audio_track_id == db_audio.id)).first() if db_audio else None

    return TaskDetail(
        id=str(task.id),
        url=task.url,
        status=task_status.code,
        cancelled=task.cancelled,
        created_at=task.created_at,
        updated_at=task.updated_at,
        download=DownloadDetail(shortcode=db_download.shortcode, file_path=db_download.file_path) if db_download else None,
        audio=AudioDetail(file_path=db_audio.file_path, duration=db_audio.duration) if db_audio else None,
        transcript=TranscriptDetail(language=db_transcript.language, topics=db_transcript.topics, file_path=db_transcript.file_path) if db_transcript else None,
        errors=_get_errors_for_task(task.id, session),
    )


def _get_task_for_user(task_id: uuid.UUID, current_user, session) -> Task | JSONResponse:
    task = session.get(Task, task_id)
    if not task or task.user_id != current_user.id:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Task not found."})
    return task


@router.get(
    "/{task_id}/video",
    responses={
        200: {"content": {"video/mp4": {}}, "description": "Reel video file."},
        404: {"model": Message, "description": "Task or video not found."},
    },
)
async def get_task_video(task_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep):
    task = _get_task_for_user(task_id, current_user, session)
    if isinstance(task, JSONResponse):
        return task

    if not task.download_id:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Video not available yet."})

    db_download = session.get(Download, task.download_id)
    if not db_download:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Video not available yet."})
    video_files = list(pathlib.Path(db_download.file_path).glob("*.mp4"))
    if not video_files:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Video file not found."})

    return FileResponse(video_files[0], media_type="video/mp4")


@router.get(
    "/{task_id}/audio",
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "Extracted audio file."},
        404: {"model": Message, "description": "Task or audio not found."},
    },
)
async def get_task_audio(task_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep):
    task = _get_task_for_user(task_id, current_user, session)
    if isinstance(task, JSONResponse):
        return task

    if not task.download_id:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Audio not available yet."})

    db_download = session.get(Download, task.download_id)
    if not db_download:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Audio not available yet."})
    db_audio = session.exec(select(AudioTrack).where(AudioTrack.download_id == db_download.id)).first()
    if not db_audio:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Audio not available yet."})

    return FileResponse(db_audio.file_path, media_type="audio/mpeg")


@router.get(
    "/{task_id}/transcript",
    responses={
        200: {"content": {"text/plain": {}}, "description": "Transcript text."},
        404: {"model": Message, "description": "Task or transcript not found."},
    },
)
async def get_task_transcript(task_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep):
    task = _get_task_for_user(task_id, current_user, session)
    if isinstance(task, JSONResponse):
        return task

    if not task.download_id:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Transcript not available yet."})

    db_download = session.get(Download, task.download_id)
    if not db_download:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Transcript not available yet."})
    db_audio = session.exec(select(AudioTrack).where(AudioTrack.download_id == db_download.id)).first()
    if not db_audio:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Transcript not available yet."})

    db_transcript = session.exec(select(Transcript).where(Transcript.audio_track_id == db_audio.id)).first()
    if not db_transcript:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": "Transcript not available yet."})

    return PlainTextResponse(pathlib.Path(db_transcript.file_path).read_text(encoding="utf-8"))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskResponse,
    responses={
        400: {
            "model": Message,
            "description": "Invalid URI. The URL is not a valid Instagram post or reel."
        }
    },
)
async def create_tasks(
    request: TaskCreateRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
):
    parsed_uri = urlparse(request.uri)

    if parsed_uri.hostname not in ("www.instagram.com", "instagram.com"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid URI. Only Instagram URLs are allowed."}
        )

    segments = parsed_uri.path.split("/")

    if len(segments) < 3 or segments[1] not in VALID_PATH_PREFIXES:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid URI. The path is not valid for an Instagram reel."}
        )

    short_code = segments[2]

    pending_status = session.exec(select(TaskStatus).where(TaskStatus.code == "pending")).one()

    db_task = Task(url=request.uri, status_code=pending_status.id, user_id=current_user.id)
    session.add(db_task)
    session.commit()
    session.refresh(db_task)

    await download.download_reel.kiq(short_code=short_code, task_id=str(db_task.id))

    return TaskResponse(task_id=str(db_task.id))


TERMINAL_STATUSES = ("completed", "failed", "cancelled")


@router.post(
    "/{task_id}/cancel",
    status_code=status.HTTP_200_OK,
    response_model=Message,
    responses={
        404: {"model": Message, "description": "Task not found."},
        409: {"model": Message, "description": "Task is in a terminal state and cannot be cancelled."},
    },
)
async def cancel_task(
    task_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
):
    task = _get_task_for_user(task_id, current_user, session)
    if isinstance(task, JSONResponse):
        return task

    current_status = session.get(TaskStatus, task.status_code)
    if current_status and current_status.code in TERMINAL_STATUSES:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": f"Task cannot be cancelled. Current status: {current_status.code}."},
        )
        
    task.cancelled = True
    session.commit()

    return Message(message="Task cancelled successfully.")
