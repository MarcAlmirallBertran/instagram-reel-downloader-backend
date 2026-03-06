import logging
import re

import httpx

from app.domain.events.reel_events import ReelDownloadFailed, ReelDownloadRequested, ReelDownloaded
from app.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus

logger = logging.getLogger(__name__)

INSTAGRAM_REEL_PATTERN = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_-]+)"
)


class ReelDownloadHandler:
    """Handles ReelDownloadRequested events and resolves the downloadable video URL."""

    def __init__(self, event_bus: InMemoryEventBus) -> None:
        self._event_bus = event_bus

    async def __call__(self, event: ReelDownloadRequested) -> None:
        logger.info("Handling ReelDownloadRequested for URL: %s", event.reel_url)

        if not INSTAGRAM_REEL_PATTERN.match(event.reel_url):
            await self._event_bus.publish(
                ReelDownloadFailed(reel_url=event.reel_url, reason="Invalid Instagram Reel URL")
            )
            return

        try:
            download_url = await self._resolve_download_url(event.reel_url)
            await self._event_bus.publish(
                ReelDownloaded(reel_url=event.reel_url, download_url=download_url)
            )
        except Exception as exc:
            logger.exception("Failed to resolve download URL for %s", event.reel_url)
            await self._event_bus.publish(
                ReelDownloadFailed(reel_url=event.reel_url, reason=str(exc))
            )

    async def _resolve_download_url(self, reel_url: str) -> str:
        """Resolve the direct video download URL for an Instagram Reel."""
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                reel_url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()

        match = re.search(r'"video_url":"(https://[^"]+)"', response.text)
        if not match:
            raise ValueError("Could not extract video URL from Instagram page")

        return match.group(1).replace(r"\u0026", "&")
