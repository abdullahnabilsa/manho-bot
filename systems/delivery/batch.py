# systems/delivery/batch.py
from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Tuple, Set, Optional
from systems.translation_pipeline.models.page_data import PageData

class BatchManager:
    """Manages in-memory batch sessions for users."""
    SESSION_TTL_SECONDS = 1800

    def __init__(self):
        self._sessions: Dict[int, Tuple[List[PageData], float]] = {}
        self._pending_compiles: Set[int] = set()
        self._session_personas: Dict[int, str] = {}
        self._session_trackers: Dict[int, int] = {}
        self._queued_files: Dict[int, List[str]] = {}
        self._custom_filenames: Dict[int, str] = {}
        self._prompt_message_ids: Dict[int, int] = {}
        self._finalizing_users: Set[int] = set()
        self._lock = asyncio.Lock()

    def _cleanup_stale_sessions(self) -> None:
        current_time = time.time()
        stale_users = [
            user_id for user_id, (_, ts) in self._sessions.items()
            if current_time - ts > self.SESSION_TTL_SECONDS
        ]
        for user_id in stale_users:
            del self._sessions[user_id]
            self._pending_compiles.discard(user_id)
            self._session_personas.pop(user_id, None)
            self._session_trackers.pop(user_id, None)
            self._queued_files.pop(user_id, None)
            self._custom_filenames.pop(user_id, None)
            self._prompt_message_ids.pop(user_id, None)
            self._finalizing_users.discard(user_id)

    async def start_session(self, user_id: int, persona_name: str) -> None:
        async with self._lock:
            self._cleanup_stale_sessions()
            if user_id not in self._sessions:
                self._sessions[user_id] = ([], time.time())
                self._session_personas[user_id] = persona_name
                self._queued_files[user_id] = []
                self._custom_filenames[user_id] = ""
                self._prompt_message_ids[user_id] = None
            self._finalizing_users.discard(user_id)

    async def get_session_persona(self, user_id: int) -> Optional[str]:
        async with self._lock:
            self._cleanup_stale_sessions()
            return self._session_personas.get(user_id)

    async def is_session_active(self, user_id: int) -> bool:
        async with self._lock:
            self._cleanup_stale_sessions()
            return user_id in self._sessions

    async def add_page_data(self, user_id: int, page_data: PageData) -> int:
        async with self._lock:
            self._cleanup_stale_sessions()
            if user_id not in self._sessions:
                self._sessions[user_id] = ([], time.time())
            data_list, _ = self._sessions[user_id]
            data_list.append(page_data)
            self._sessions[user_id] = (data_list, time.time())
            return len(data_list)

    async def get_session_data(self, user_id: int) -> List[PageData]:
        async with self._lock:
            self._cleanup_stale_sessions()
            data, _ = self._sessions.get(user_id, ([], time.time()))
            return data

    async def clear_session(self, user_id: int) -> None:
        async with self._lock:
            if user_id in self._sessions:
                del self._sessions[user_id]
            self._session_personas.pop(user_id, None)
            self._session_trackers.pop(user_id, None)
            self._queued_files.pop(user_id, None)
            self._custom_filenames.pop(user_id, None)
            self._prompt_message_ids.pop(user_id, None)
            self._finalizing_users.discard(user_id)

    async def set_pending_compile(self, user_id: int) -> None:
        async with self._lock:
            self._pending_compiles.add(user_id)

    async def is_pending_compile(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._pending_compiles

    async def clear_pending_compile(self, user_id: int) -> None:
        async with self._lock:
            self._pending_compiles.discard(user_id)

    async def set_tracker(self, user_id: int, message_id: int) -> None:
        async with self._lock:
            self._session_trackers[user_id] = message_id

    async def get_tracker(self, user_id: int) -> Optional[int]:
        async with self._lock:
            return self._session_trackers.get(user_id)

    async def add_queued_file(self, user_id: int, file_name: str) -> None:
        async with self._lock:
            if user_id not in self._queued_files:
                self._queued_files[user_id] = []
            self._queued_files[user_id].append(file_name)

    async def remove_queued_file(self, user_id: int, file_name: str) -> None:
        async with self._lock:
            if user_id in self._queued_files and file_name in self._queued_files[user_id]:
                self._queued_files[user_id].remove(file_name)

    async def get_queued_files(self, user_id: int) -> List[str]:
        async with self._lock:
            return list(self._queued_files.get(user_id, []))

    async def clear_queued_files(self, user_id: int) -> None:
        async with self._lock:
            self._queued_files[user_id] = []

    async def set_custom_filename(self, user_id: int, filename: str) -> None:
        async with self._lock:
            self._custom_filenames[user_id] = filename

    async def get_custom_filename(self, user_id: int) -> Optional[str]:
        async with self._lock:
            self._cleanup_stale_sessions()
            return self._custom_filenames.get(user_id)

    async def set_prompt_message_id(self, user_id: int, message_id: int) -> None:
        async with self._lock:
            self._prompt_message_ids[user_id] = message_id

    async def get_prompt_message_id(self, user_id: int) -> Optional[int]:
        async with self._lock:
            return self._prompt_message_ids.get(user_id)

    async def set_finalizing(self, user_id: int, status: bool) -> None:
        async with self._lock:
            if status:
                self._finalizing_users.add(user_id)
            else:
                self._finalizing_users.discard(user_id)

    async def is_finalizing(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._finalizing_users