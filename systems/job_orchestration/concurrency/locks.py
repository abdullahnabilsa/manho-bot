# systems/job_orchestration/concurrency/locks.py
from __future__ import annotations

import asyncio
from typing import Dict


class LockManager:
    """
    Manages in-memory semaphores and locks for:
    - Per-User concurrency (Semaphore — dynamic limit).
    - Chat Throttling (Lock — Telegram API safety).
    - Tracker UI safety (Lock — prevent race on message edits).
    """
    def __init__(self) -> None:
        self._user_semaphores: Dict[int, asyncio.Semaphore] = {}
        self._chat_locks: Dict[int, asyncio.Lock] = {}
        self._tracker_locks: Dict[int, asyncio.Lock] = {}
        self._creation_lock = asyncio.Lock()

    async def get_user_semaphore(self, user_id: int) -> asyncio.Semaphore:
        async with self._creation_lock:
            if user_id not in self._user_semaphores:
                self._user_semaphores[user_id] = asyncio.Semaphore(1)
            return self._user_semaphores[user_id]

    async def set_user_concurrency_limit(self, user_id: int, limit: int) -> None:
        """Replace the user's semaphore with a new one of the specified limit."""
        async with self._creation_lock:
            self._user_semaphores[user_id] = asyncio.Semaphore(limit)

    async def reset_user_concurrency(self, user_id: int) -> None:
        """Reset the user's semaphore to 1 (sequential processing)."""
        async with self._creation_lock:
            self._user_semaphores[user_id] = asyncio.Semaphore(1)

    async def get_chat_lock(self, chat_id: int) -> asyncio.Lock:
        async with self._creation_lock:
            if chat_id not in self._chat_locks:
                self._chat_locks[chat_id] = asyncio.Lock()
            return self._chat_locks[chat_id]

    async def get_tracker_lock(self, user_id: int) -> asyncio.Lock:
        async with self._creation_lock:
            if user_id not in self._tracker_locks:
                self._tracker_locks[user_id] = asyncio.Lock()
            return self._tracker_locks[user_id]