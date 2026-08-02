# systems/job_orchestration/concurrency/locks.py
from __future__ import annotations

import asyncio
from typing import Dict

class LockManager:
    """
    Manages in-memory locks for Per-User sequential processing, 
    Chat Throttling (Telegram API safety), and Tracker UI safety.
    """
    def __init__(self):
        self._user_locks: Dict[int, asyncio.Lock] = {}
        self._chat_locks: Dict[int, asyncio.Lock] = {}
        self._tracker_locks: Dict[int, asyncio.Lock] = {}
        self._creation_lock = asyncio.Lock()

    async def get_user_lock(self, user_id: int) -> asyncio.Lock:
        async with self._creation_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = asyncio.Lock()
            return self._user_locks[user_id]

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