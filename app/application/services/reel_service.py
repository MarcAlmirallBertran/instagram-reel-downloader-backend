import asyncio
import logging

from app.domain.events.reel_events import ReelDownloadFailed, ReelDownloadRequested, ReelDownloaded
from app.domain.models.reel import DownloadStatus, ReelDownloadResult
from app.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT_SECONDS = 30


class ReelService:
    """Application service that orchestrates reel download requests via the event bus."""

    def __init__(self, event_bus: InMemoryEventBus) -> None:
        self._event_bus = event_bus
        self._event_bus.subscribe(ReelDownloaded, self._on_downloaded)
        self._event_bus.subscribe(ReelDownloadFailed, self._on_failed)

    async def request_download(self, reel_url: str) -> ReelDownloadResult:
        """Publish a ReelDownloadRequested event and await the outcome."""
        result: ReelDownloadResult | None = None
        done = asyncio.Event()

        async def on_downloaded(event: ReelDownloaded) -> None:
            nonlocal result
            result = ReelDownloadResult(
                reel_url=event.reel_url,
                status=DownloadStatus.COMPLETED,
                download_url=event.download_url,
            )
            done.set()

        async def on_failed(event: ReelDownloadFailed) -> None:
            nonlocal result
            result = ReelDownloadResult(
                reel_url=event.reel_url,
                status=DownloadStatus.FAILED,
                error=event.reason,
            )
            done.set()

        self._event_bus.subscribe(ReelDownloaded, on_downloaded)
        self._event_bus.subscribe(ReelDownloadFailed, on_failed)

        try:
            await self._event_bus.publish(ReelDownloadRequested(reel_url=reel_url))
            try:
                await asyncio.wait_for(done.wait(), timeout=_DOWNLOAD_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                return ReelDownloadResult(
                    reel_url=reel_url,
                    status=DownloadStatus.FAILED,
                    error="Download timed out",
                )
        finally:
            self._event_bus.unsubscribe(ReelDownloaded, on_downloaded)
            self._event_bus.unsubscribe(ReelDownloadFailed, on_failed)

        if result is None:
            return ReelDownloadResult(
                reel_url=reel_url,
                status=DownloadStatus.FAILED,
                error="No result received",
            )

        return result

    async def _on_downloaded(self, event: ReelDownloaded) -> None:
        logger.info("Reel downloaded: %s -> %s", event.reel_url, event.download_url)

    async def _on_failed(self, event: ReelDownloadFailed) -> None:
        logger.warning("Reel download failed: %s — %s", event.reel_url, event.reason)
