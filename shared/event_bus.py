# shared/event_bus.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List

logger = logging.getLogger(__name__)

class EventBus:
    """
    Lightweight async event bus to decouple systems.
    """
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], Awaitable[None]]]] = {}

    def subscribe(self, event: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(handler)

    async def publish(self, event: str, payload: Any = None) -> None:
        if event not in self._subscribers:
            return
        
        handlers = self._subscribers[event]
        tasks = [handler(payload) for handler in handlers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"EventBus handler error for event '{event}': {result}", exc_info=result)