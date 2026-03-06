from functools import lru_cache

from app.application.event_handlers.reel_handlers import ReelDownloadHandler
from app.application.services.reel_service import ReelService
from app.domain.events.reel_events import ReelDownloadRequested
from app.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus


@lru_cache
def get_event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@lru_cache
def get_reel_service() -> ReelService:
    event_bus = get_event_bus()
    handler = ReelDownloadHandler(event_bus)
    event_bus.subscribe(ReelDownloadRequested, handler)
    return ReelService(event_bus)
