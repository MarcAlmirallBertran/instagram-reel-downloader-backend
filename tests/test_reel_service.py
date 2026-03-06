import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.application.event_handlers.reel_handlers import ReelDownloadHandler
from app.application.services.reel_service import ReelService
from app.domain.models.reel import DownloadStatus
from app.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def service(event_bus: InMemoryEventBus) -> ReelService:
    handler = ReelDownloadHandler(event_bus)
    from app.domain.events.reel_events import ReelDownloadRequested

    event_bus.subscribe(ReelDownloadRequested, handler)
    return ReelService(event_bus)


async def test_request_download_success(service: ReelService) -> None:
    with patch.object(
        ReelDownloadHandler,
        "_resolve_download_url",
        new=AsyncMock(return_value="https://cdn.example.com/video.mp4"),
    ):
        result = await service.request_download("https://www.instagram.com/reel/CxABCDEFGH")

    assert result.status == DownloadStatus.COMPLETED
    assert result.download_url == "https://cdn.example.com/video.mp4"


async def test_request_download_invalid_url(service: ReelService) -> None:
    result = await service.request_download("https://example.com/not-a-reel")
    assert result.status == DownloadStatus.FAILED
    assert result.error is not None


async def test_request_download_timeout(event_bus: InMemoryEventBus) -> None:
    """If no handler publishes a result, the service should return a timeout error."""
    service = ReelService(event_bus)  # no handler subscribed — event will not be resolved

    with patch("app.application.services.reel_service._DOWNLOAD_TIMEOUT_SECONDS", 0.05):
        result = await service.request_download("https://www.instagram.com/reel/CxABCDEFGH")

    assert result.status == DownloadStatus.FAILED
    assert "timed out" in (result.error or "").lower()
