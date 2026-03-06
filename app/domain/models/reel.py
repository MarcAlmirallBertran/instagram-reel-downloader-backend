from enum import Enum

from pydantic import BaseModel, HttpUrl


class DownloadStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ReelDownloadRequest(BaseModel):
    reel_url: HttpUrl


class ReelDownloadResult(BaseModel):
    reel_url: str
    status: DownloadStatus
    download_url: str | None = None
    error: str | None = None
