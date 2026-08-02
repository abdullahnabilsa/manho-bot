# systems/access_control/manager.py
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Dict, Tuple
from shared.database import Database

logger = logging.getLogger(__name__)

class AccessManager:
    """Manages access control hierarchy and join requests via SQLite."""
    
    def __init__(self, db: Database, super_admin_ids: str = "") -> None:
        self._db = db
        self._super_admin_ids = [uid.strip() for uid in super_admin_ids.split(",") if uid.strip()]
        self._pending_requests: Dict[int, List[Tuple[int, int]]] = {}
        self._request_cooldowns: Dict[int, float] = {}
        self._lock = asyncio.Lock()

    def is_super_admin(self, user_id: int) -> bool:
        return str(user_id) in self._super_admin_ids

    async def is_admin(self, user_id: int) -> bool:
        if self.is_super_admin(user_id): return True
        row = await self._db.fetchone("SELECT 1 FROM users_access WHERE user_id = ? AND role = 'admin'", (user_id,))
        return row is not None

    async def is_authorized(self, user_id: int) -> bool:
        if self.is_super_admin(user_id): return True
        row = await self._db.fetchone("SELECT 1 FROM users_access WHERE user_id = ?", (user_id,))
        return row is not None

    async def is_join_requests_open(self) -> bool:
        row = await self._db.fetchone("SELECT value FROM meta WHERE key = 'join_requests_open'")
        return row is not None and row[0] == 'true'

    async def set_join_requests(self, status: bool) -> None:
        val = 'true' if status else 'false'
        await self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('join_requests_open', ?)", (val,))

    async def add_user(self, user_id: int) -> bool:
        if self.is_super_admin(user_id): return False
        existing = await self._db.fetchone("SELECT role FROM users_access WHERE user_id = ?", (user_id,))
        if existing: return False
        await self._db.execute("INSERT INTO users_access (user_id, role) VALUES (?, 'user')", (user_id,))
        return True

    async def remove_user(self, user_id: int) -> bool:
        if self.is_super_admin(user_id): return False
        existing = await self._db.fetchone("SELECT 1 FROM users_access WHERE user_id = ? AND role = 'user'", (user_id,))
        if not existing: return False
        await self._db.execute("DELETE FROM users_access WHERE user_id = ? AND role = 'user'", (user_id,))
        return True

    async def add_admin(self, user_id: int) -> bool:
        if self.is_super_admin(user_id): return False
        await self._db.execute("INSERT OR REPLACE INTO users_access (user_id, role) VALUES (?, 'admin')", (user_id,))
        return True

    async def remove_admin(self, user_id: int) -> bool:
        if self.is_super_admin(user_id): return False
        existing = await self._db.fetchone("SELECT 1 FROM users_access WHERE user_id = ? AND role = 'admin'", (user_id,))
        if not existing: return False
        await self._db.execute("DELETE FROM users_access WHERE user_id = ? AND role = 'admin'", (user_id,))
        return True

    async def get_admins(self) -> List[str]:
        rows = await self._db.fetchall("SELECT user_id FROM users_access WHERE role = 'admin'")
        db_admins = [str(row[0]) for row in rows]
        all_admins = list(set(self._super_admin_ids + db_admins))
        return all_admins

    async def get_users(self) -> List[str]:
        rows = await self._db.fetchall("SELECT user_id FROM users_access WHERE role = 'user'")
        return [str(row[0]) for row in rows]

    async def is_on_cooldown(self, user_id: int) -> bool:
        async with self._lock:
            last_request = self._request_cooldowns.get(user_id)
            if last_request and (time.time() - last_request < 60):
                return True
            return False

    async def update_cooldown(self, user_id: int) -> None:
        async with self._lock:
            self._request_cooldowns[user_id] = time.time()

    async def track_request(self, user_id: int, admin_id: int, message_id: int) -> None:
        async with self._lock:
            if user_id not in self._pending_requests:
                self._pending_requests[user_id] = []
            self._pending_requests[user_id].append((admin_id, message_id))

    async def get_pending_requests(self, user_id: int) -> List[Tuple[int, int]]:
        async with self._lock:
            return list(self._pending_requests.get(user_id, []))

    async def clear_requests(self, user_id: int) -> None:
        async with self._lock:
            self._pending_requests.pop(user_id, None)