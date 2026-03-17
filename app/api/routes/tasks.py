import io
import logging
import pathlib
import uuid
import zipfile
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Query, status
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    StreamingResponse,
)
from pydantic.main import BaseModel
from sqlmodel import col, select

from app.api.deps import CurrentUserDep, SessionDep
from app.models import (
    File,
    Task,
    TaskError,
    TaskStatus,
    TaskStep,
)
from app.services import download

logger = logging.getLogger(__name__)

VALID_PATH_PREFIXES = ["reel"]
router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    task_id: str


class ErrorDetail(BaseModel):
    step: str
    message: str
    detail: str | None
    created_at: datetime


class TaskBase(BaseModel):
    id: str
    short_code: str
    status: str
    cancelled: bool
    created_at: datetime
    updated_at: datetime
    errors: list[ErrorDetail]


class VideoDetail(BaseModel):
    shortcode: str
    file_path: str
    mime_type: str


class AudioDetail(BaseModel):
    file_path: str
    mime_type: str


class TranscriptDetail(BaseModel):
    language:   str | None
    topics:     str | None
    file_path:  str
    mime_type:  str


class TaskDetail(TaskBase):
    video: VideoDetail | None
    audio: AudioDetail | None
    transcript: TranscriptDetail | None


class Message(BaseModel):
    message: str


class TaskCreateRequest(BaseModel):
    uri: str


def _get_errors_for_task(task_id: uuid.UUID, session) -> list[ErrorDetail]:
    errors = session.exec(select(TaskError).where(TaskError.task_id == task_id)).all()
    steps = {s.id: s.code for s in session.exec(select(TaskStep)).all()}
    return [
        ErrorDetail(
            step=steps[e.step_code],
            message=e.message,
            detail=e.detail,
            created_at=e.created_at,
        )
        for e in errors
    ]


@router.get("", status_code=status.HTTP_200_OK, response_model=list[TaskBase])
async def list_tasks(
    session: SessionDep,
    current_user: CurrentUserDep,
    status: str | None = Query(
        default=None,
        description="Filter by task status (e.g. pending, in_progress, processing, completed, failed, cancelled)",
    ),
    sort_by: Literal["created_at", "updated_at"] = Query(
        default="created_at", description="Field to sort by"
    ),
    sort_order: Literal["asc", "desc"] = Query(
        default="desc", description="Sort order"
    ),
):
    query = select(Task).where(Task.user_id == current_user.id)

    if status:
        status_row = session.exec(
            select(TaskStatus).where(TaskStatus.code == status)
        ).one_or_none()
        if status_row:
            query = query.where(Task.status_code == status_row.id)
        else:
            return []

    sort_column = (
        col(Task.updated_at) if sort_by == "updated_at" else col(Task.created_at)
    )
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    tasks = session.exec(query).all()
    statuses = {s.id: s.code for s in session.exec(select(TaskStatus)).all()}
    return [
        TaskBase(
            id=str(t.id),
            short_code=t.short_code,
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
async def get_task(
    task_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
):
    task = _get_task_for_user(task_id, current_user, session)
    if isinstance(task, JSONResponse):
        return task

    task_status = session.get(TaskStatus, task.status_code)
    if not task_status:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Task not found."},
        )

    db_video = session.get(File, task.video_id) if task.video_id else None
    db_audio = (
        session.exec(
            select(File).where(File.id == task.audio_id)
        ).one()
        if task.audio_id
        else None
    )
    db_transcript = (
        session.exec(
            select(File).where(File.id == task.transcript_id)
        ).one()
        if task.transcript_id
        else None
    )

    return TaskDetail(
        id=str(task.id),
        short_code=task.short_code,
        status=task_status.code,
        cancelled=task.cancelled,
        created_at=task.created_at,
        updated_at=task.updated_at,
        video=VideoDetail(
            shortcode=task.short_code,
            file_path=db_video.path,
            mime_type=db_video.mime_type,
        )
        if db_video
        else None,
        audio=AudioDetail(
            file_path=db_audio.path,
            mime_type=db_audio.mime_type,
        )
        if db_audio
        else None,
        transcript=TranscriptDetail(
            language=task.language,
            topics=task.topics,
            file_path=db_transcript.path,
            mime_type=db_transcript.mime_type,
        )
        if db_transcript
        else None,
        errors=_get_errors_for_task(task.id, session),
    )


def _get_task_for_user(
    task_id: uuid.UUID, current_user, session
) -> Task | JSONResponse:
    task = session.get(Task, task_id)
    if not task or task.user_id != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Task not found."},
        )
    return task


FILE_TYPE_MAP = {
    "video": "video_id",
    "audio": "audio_id",
    "transcript": "transcript_id",
}


@router.get(
    "/{task_id}/files/{file_type}",
    responses={
        200: {"description": "Requested file."},
        404: {"model": Message, "description": "Task or file not found."},
    },
    status_code=status.HTTP_200_OK,
    response_class=FileResponse,
)
async def get_task_file(
    task_id: uuid.UUID,
    file_type: Literal["video", "audio", "transcript"],
    session: SessionDep,
    current_user: CurrentUserDep,
):
    task = _get_task_for_user(task_id, current_user, session)
    if isinstance(task, JSONResponse):
        return task

    file_id = getattr(task, FILE_TYPE_MAP[file_type])
    if not file_id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": f"{file_type.capitalize()} file not found."},
        )

    db_file = session.exec(select(File).where(File.id == file_id)).one()
    return FileResponse(db_file.path, media_type=db_file.mime_type)


@router.get(
    "/{task_id}/files",
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "ZIP archive with all available task files.",
        },
        404: {"model": Message, "description": "Task or files not found."},
    },
    status_code=status.HTTP_200_OK,
    response_class=FileResponse,
)
async def get_task_files(
    task_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
):
    task = _get_task_for_user(task_id, current_user, session)
    if isinstance(task, JSONResponse):
        return task

    if not task.video_id and not task.audio_id and not task.transcript_id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Files not found."},
        )

    db_video = session.exec(select(File).where(File.id == task.video_id)).one()

    dir = pathlib.Path(db_video.path).parent
    
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in dir.iterdir():
            if not file_path.is_file():
                continue
            zf.write(file_path, arcname=file_path.name)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={task_id}.zip"},
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskResponse,
    responses={
        400: {
            "model": Message,
            "description": "Invalid URI. The URL is not a valid Instagram post or reel.",
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
            content={"message": "Invalid URI. Only Instagram URLs are allowed."},
        )

    segments = parsed_uri.path.split("/")

    if len(segments) < 3 or segments[1] not in VALID_PATH_PREFIXES:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "message": "Invalid URI. The path is not valid for an Instagram reel."
            },
        )

    short_code = segments[2]

    pending_status = session.exec(
        select(TaskStatus).where(TaskStatus.code == "pending")
    ).one()

    db_task = Task(
        short_code=short_code,
        status_code=pending_status.id,
        user_id=current_user.id,
    )
    session.add(db_task)
    session.commit()
    session.refresh(db_task)

    await download.download_reel.kiq(task_id=str(db_task.id))

    return TaskResponse(task_id=str(db_task.id))


TERMINAL_STATUSES = ("completed", "failed", "cancelled")


@router.post(
    "/{task_id}/cancel",
    status_code=status.HTTP_200_OK,
    response_model=Message,
    responses={
        404: {"model": Message, "description": "Task not found."},
        409: {
            "model": Message,
            "description": "Task is in a terminal state and cannot be cancelled.",
        },
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
            content={
                "message": f"Task cannot be cancelled. Current status: {current_status.code}."
            },
        )

    task.cancelled = True
    session.commit()

    return Message(message="Task cancelled successfully.")
