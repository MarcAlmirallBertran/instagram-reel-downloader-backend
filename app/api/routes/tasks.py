import logging
from urllib.parse import urlparse

from fastapi import APIRouter, status
from pydantic.main import BaseModel
from fastapi.responses import JSONResponse
from app.services import download

logger = logging.getLogger(__name__)


VALID_PATH_PREFIXES = ("reel")
router = APIRouter(prefix="/tasks", tags=["tasks"])


class Task(BaseModel):
    task_id: str

 
class Message(BaseModel):
    message: str
    

class TaskCreateRequest(BaseModel):
    uri: str    


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Task,
    responses={
        400: {
            "model": Message,
            "description": "Invalid URI. The URL is not a valid Instagram post or reel."
        }
    },
)
async def create_tasks(request: TaskCreateRequest):
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
    
    task = await download.download_reel.kiq(short_code)
    
    return Task(task_id=task.task_id)
