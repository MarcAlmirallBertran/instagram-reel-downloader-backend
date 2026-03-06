import asyncio

import pytest

from app.domain.events.reel_events import ReelDownloadFailed, ReelDownloadRequested, ReelDownloaded
from app.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


async def test_publish_triggers_subscribed_handler(event_bus: InMemoryEventBus) -> None:
    received: list[ReelDownloadRequested] = []

    async def handler(event: ReelDownloadRequested) -> None:
        received.append(event)

    event_bus.subscribe(ReelDownloadRequested, handler)
    await event_bus.publish(ReelDownloadRequested(reel_url="https://www.instagram.com/reel/abc123"))

    assert len(received) == 1
    assert received[0].reel_url == "https://www.instagram.com/reel/abc123"


async def test_publish_multiple_handlers(event_bus: InMemoryEventBus) -> None:
    calls: list[str] = []

    async def handler_a(event: ReelDownloadRequested) -> None:
        calls.append("a")

    async def handler_b(event: ReelDownloadRequested) -> None:
        calls.append("b")

    event_bus.subscribe(ReelDownloadRequested, handler_a)
    event_bus.subscribe(ReelDownloadRequested, handler_b)
    await event_bus.publish(ReelDownloadRequested(reel_url="https://www.instagram.com/reel/abc123"))

    assert sorted(calls) == ["a", "b"]


async def test_publish_no_handlers_does_not_raise(event_bus: InMemoryEventBus) -> None:
    await event_bus.publish(ReelDownloadRequested(reel_url="https://www.instagram.com/reel/abc123"))


async def test_publish_only_triggers_matching_event_type(event_bus: InMemoryEventBus) -> None:
    downloaded_received: list[ReelDownloaded] = []

    async def on_downloaded(event: ReelDownloaded) -> None:
        downloaded_received.append(event)

    event_bus.subscribe(ReelDownloaded, on_downloaded)
    await event_bus.publish(ReelDownloadRequested(reel_url="https://www.instagram.com/reel/abc123"))

    assert len(downloaded_received) == 0


async def test_base_event_fields_auto_populated(event_bus: InMemoryEventBus) -> None:
    event = ReelDownloadRequested(reel_url="https://www.instagram.com/reel/abc123")
    assert event.event_id is not None
    assert event.occurred_at is not None
