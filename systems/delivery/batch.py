# File: systems/delivery/batch.py
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
        self._session_modes: Dict[int, str] = {}
        self._session_trackers: Dict[int, int] = {}
        self._queued_files: Dict[int, List[str]] = {}
        self._custom_filenames: Dict[int, str] = {}
        self._prompt_message_ids: Dict[int, int] = {}
        self._finalizing_users: Set[int] = set()
        
        self._received_counts: Dict[int, int] = {}
        self._session_start_times: Dict[int, float] = {}
        
        # Intake & Caching Engine
        self._pending_file_ids: Dict[int, List[Tuple[str, str, int]]] = {}
        
        # Decoupled Compile Lock
        self._compile_locks: Set[int] = set()
        
        # Race & Flood Control Isolation
        self._last_tracker_updates: Dict[int, float] = {}
        self._force_update_tracker: Set[int] = set()
        
        # Local In-Memory Locks
        self._tracker_locks: Dict[int, asyncio.Lock] = {}
        self._chat_locks: Dict[int, asyncio.Lock] = {}
        self._locks_creation_lock = asyncio.Lock()
        
        self._lock = asyncio.Lock()
        self._received_counts_lock = asyncio.Lock()

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
            self._session_modes.pop(user_id, None)
            self._session_trackers.pop(user_id, None)
            self._queued_files.pop(user_id, None)
            self._custom_filenames.pop(user_id, None)
            self._prompt_message_ids.pop(user_id, None)
            self._received_counts.pop(user_id, None)
            self._session_start_times.pop(user_id, None)
            self._last_tracker_updates.pop(user_id, None)
            self._force_update_tracker.discard(user_id)
            self._finalizing_users.discard(user_id)
            self._pending_file_ids.pop(user_id, None)
            self._compile_locks.discard(user_id)

    async def start_session(self, user_id: int, persona_name: str, session_mode: str) -> None:
        async with self._lock:
            self._cleanup_stale_sessions()
            if user_id not in self._sessions:
                self._sessions[user_id] = ([], time.time())
                self._session_personas[user_id] = persona_name
                self._session_modes[user_id] = session_mode
                self._queued_files[user_id] = []
                self._custom_filenames[user_id] = ""
                self._prompt_message_ids[user_id] = None
                self._received_counts[user_id] = 0
                self._session_start_times[user_id] = time.time()
                self._last_tracker_updates[user_id] = 0.0
                self._pending_file_ids[user_id] = []
            self._finalizing_users.discard(user_id)
            self._compile_locks.discard(user_id)

    async def get_session_persona(self, user_id: int) -> Optional[str]:
        async with self._lock:
            self._cleanup_stale_sessions()
            return self._session_personas.get(user_id)

    async def get_session_mode(self, user_id: int) -> Optional[str]:
        async with self._lock:
            self._cleanup_stale_sessions()
            return self._session_modes.get(user_id)

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
            self._session_modes.pop(user_id, None)
            self._session_trackers.pop(user_id, None)
            self._queued_files.pop(user_id, None)
            self._custom_filenames.pop(user_id, None)
            self._prompt_message_ids.pop(user_id, None)
            self._session_start_times.pop(user_id, None)
            self._last_tracker_updates.pop(user_id, None)
            self._force_update_tracker.discard(user_id)
            self._finalizing_users.discard(user_id)
            self._pending_compiles.discard(user_id)
            self._pending_file_ids.pop(user_id, None)
            self._compile_locks.discard(user_id)
            self._received_counts.pop(user_id, None)

    async def set_pending_compile(self, user_id: int) -> None:
        async with self._lock:
            self._pending_compiles.add(user_id)

    async def is_pending_compile(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._pending_compiles

    async def clear_pending_compile(self, user_id: int) -> None:
        async with self._lock:
            self._pending_compiles.discard(user_id)

    async def try_acquire_compile_lock(self, user_id: int) -> bool:
        async with self._lock:
            if user_id in self._compile_locks:
                return False
            self._compile_locks.add(user_id)
            return True

    async def set_tracker(self, user_id: int, message_id: Optional[int]) -> None:
        async with self._lock:
            self._session_trackers[user_id] = message_id

    async def get_tracker(self, user_id: int) -> Optional[int]:
        async with self._lock:
            return self._session_trackers.get(user_id)

    async def increment_received_count(self, user_id: int) -> int:
        async with self._received_counts_lock:
            self._received_counts[user_id] = self._received_counts.get(user_id, 0) + 1
            return self._received_counts[user_id]

    async def get_received_count(self, user_id: int) -> int:
        async with self._received_counts_lock:
            return self._received_counts.get(user_id, 0)

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

    async def get_session_start_time(self, user_id: int) -> Optional[float]:
        async with self._lock:
            self._cleanup_stale_sessions()
            return self._session_start_times.get(user_id)

    # --- LOCAL LOCKS ENGINE ---

    async def acquire_tracker_lock(self, user_id: int) -> None:
        async with self._locks_creation_lock:
            if user_id not in self._tracker_locks:
                self._tracker_locks[user_id] = asyncio.Lock()
        await self._tracker_locks[user_id].acquire()

    async def release_tracker_lock(self, user_id: int) -> None:
        lock = self._tracker_locks.get(user_id)
        if lock and lock.locked():
            lock.release()

    async def acquire_chat_send_lock(self, chat_id: int) -> None:
        async with self._locks_creation_lock:
            if chat_id not in self._chat_locks:
                self._chat_locks[chat_id] = asyncio.Lock()
        await self._chat_locks[chat_id].acquire()

    async def release_chat_send_lock(self, chat_id: int) -> None:
        lock = self._chat_locks.get(chat_id)
        if lock and lock.locked():
            lock.release()

    # --- TRACKER DEBOUNCE ENGINE ---

    async def force_update_tracker(self, user_id: int) -> None:
        """Forces the next tracker update to bypass the debounce check."""
        async with self._lock:
            self._force_update_tracker.add(user_id)

    async def can_update_tracker(self, user_id: int, debounce_sec: float = 0.8) -> bool:
        """
        Checks if the tracker can be updated based on the debounce time.
        If a force update is requested, it bypasses the check and consumes the flag.
        """
        async with self._lock:
            if user_id in self._force_update_tracker:
                self._force_update_tracker.discard(user_id)
                self._last_tracker_updates[user_id] = time.time()
                return True
                
            last_update = self._last_tracker_updates.get(user_id, 0.0)
            if time.time() - last_update < debounce_sec:
                return False
                
            self._last_tracker_updates[user_id] = time.time()
            return True

    # --- INTAKE & CACHING ENGINE ---

    async def add_pending_file(self, user_id: int, file_id: str, file_name: str, photo_message_id: int) -> int:
        async with self._lock:
            self._cleanup_stale_sessions()
            if user_id not in self._pending_file_ids:
                self._pending_file_ids[user_id] = []
            self._pending_file_ids[user_id].append((file_id, file_name, photo_message_id))
            return len(self._pending_file_ids[user_id])

    async def get_pending_files(self, user_id: int) -> List[Tuple[str, str, int]]:
        async with self._lock:
            self._cleanup_stale_sessions()
            return list(self._pending_file_ids.get(user_id, []))

    async def clear_pending_files(self, user_id: int) -> None:
        async with self._lock:
            self._pending_file_ids[user_id] = []