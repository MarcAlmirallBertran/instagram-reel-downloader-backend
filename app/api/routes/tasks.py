import logging
from urllib.parse import urlparse

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic.main import BaseModel

from sqlmodel import select

from app.api.deps import SessionDep
from app.models import Task, TaskStatus
from app.services import download

logger = logging.getLogger(__name__)

VALID_PATH_PREFIXES = ("reel")
router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    task_id: str


class Message(BaseModel):
    message: str


class TaskCreateRequest(BaseModel):
    uri: str


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

    db_task = Task(url=request.uri, status_code=pending_status.id)
    session.add(db_task)
    session.commit()
    session.refresh(db_task)

    await download.download_reel.kiq(short_code, str(db_task.id))

    return TaskResponse(task_id=str(db_task.id))
