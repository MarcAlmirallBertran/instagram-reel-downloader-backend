from unittest.mock import AsyncMock, patch

import pytest

from app.application.event_handlers.reel_handlers import ReelDownloadHandler
from app.domain.events.reel_events import ReelDownloadFailed, ReelDownloadRequested, ReelDownloaded
from app.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def handler(event_bus: InMemoryEventBus) -> ReelDownloadHandler:
    return ReelDownloadHandler(event_bus)


async def test_invalid_url_publishes_failed_event(
    event_bus: InMemoryEventBus, handler: ReelDownloadHandler
) -> None:
    failed_events: list[ReelDownloadFailed] = []

    async def on_failed(event: ReelDownloadFailed) -> None:
        failed_events.append(event)

    event_bus.subscribe(ReelDownloadFailed, on_failed)
    await handler(ReelDownloadRequested(reel_url="https://example.com/not-a-reel"))

    assert len(failed_events) == 1
    assert "Invalid" in failed_events[0].reason


async def test_valid_url_publishes_downloaded_event(
    event_bus: InMemoryEventBus, handler: ReelDownloadHandler
) -> None:
    downloaded_events: list[ReelDownloaded] = []

    async def on_downloaded(event: ReelDownloaded) -> None:
        downloaded_events.append(event)

    event_bus.subscribe(ReelDownloaded, on_downloaded)

    with patch.object(
        handler,
        "_resolve_download_url",
        new=AsyncMock(return_value="https://cdn.example.com/video.mp4"),
    ):
        await handler(
            ReelDownloadRequested(reel_url="https://www.instagram.com/reel/CxABCDEFGH")
        )

    assert len(downloaded_events) == 1
    assert downloaded_events[0].download_url == "https://cdn.example.com/video.mp4"


async def test_resolve_error_publishes_failed_event(
    event_bus: InMemoryEventBus, handler: ReelDownloadHandler
) -> None:
    failed_events: list[ReelDownloadFailed] = []

    async def on_failed(event: ReelDownloadFailed) -> None:
        failed_events.append(event)

    event_bus.subscribe(ReelDownloadFailed, on_failed)

    with patch.object(
        handler,
        "_resolve_download_url",
        new=AsyncMock(side_effect=ValueError("Could not extract video URL from Instagram page")),
    ):
        await handler(
            ReelDownloadRequested(reel_url="https://www.instagram.com/reel/CxABCDEFGH")
        )

    assert len(failed_events) == 1
    assert "Could not extract" in failed_events[0].reason
