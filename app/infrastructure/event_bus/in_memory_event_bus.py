import asyncio
import logging
from collections import defaultdict
from typing import Callable, Type

from app.domain.events.base import BaseEvent

logger = logging.getLogger(__name__)


class InMemoryEventBus:
    """Thread-safe, async in-memory event bus for publishing and subscribing to domain events."""

    def __init__(self) -> None:
        self._handlers: dict[Type[BaseEvent], list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: Type[BaseEvent], handler: Callable) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)
        logger.debug(
            "Subscribed %s to %s",
            getattr(handler, "__name__", type(handler).__name__),
            event_type.__name__,
        )

    def unsubscribe(self, event_type: Type[BaseEvent], handler: Callable) -> None:
        """Remove a previously registered handler for a specific event type."""
        try:
            self._handlers[event_type].remove(handler)
            logger.debug(
                "Unsubscribed %s from %s",
                getattr(handler, "__name__", type(handler).__name__),
                event_type.__name__,
            )
        except ValueError:
            pass

    async def publish(self, event: BaseEvent) -> None:
        """Publish an event to all registered handlers."""
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            logger.debug("No handlers registered for %s", type(event).__name__)
            return

        logger.debug("Publishing %s to %d handler(s)", type(event).__name__, len(handlers))
        await asyncio.gather(*[handler(event) for handler in handlers])
