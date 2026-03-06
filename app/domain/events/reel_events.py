from dataclasses import dataclass, field

from app.domain.events.base import BaseEvent


@dataclass
class ReelDownloadRequested(BaseEvent):
    reel_url: str = field(default="")


@dataclass
class ReelDownloaded(BaseEvent):
    reel_url: str = field(default="")
    download_url: str = field(default="")


@dataclass
class ReelDownloadFailed(BaseEvent):
    reel_url: str = field(default="")
    reason: str = field(default="")
