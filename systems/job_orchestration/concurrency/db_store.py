# systems/job_orchestration/concurrency/db_store.py
from __future__ import annotations
import time
import logging
from typing import Optional, Tuple, List
from shared.database import Database

logger = logging.getLogger(__name__)

class ConcurrencyDBStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_global_limit(self) -> int:
        row = await self._db.fetchone("SELECT value FROM meta WHERE key = 'global_concurrency_limit'")
        if not row:
            await self.set_global_limit(3)
            return 3
        return int(row[0])

    async def set_global_limit(self, limit: int) -> int:
        limit = max(1, min(5, limit))
        await self._db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('global_concurrency_limit', ?)", 
            (str(limit),)
        )
        return limit

    async def grant_permanent_access(self, user_id: int) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO concurrency_access (user_id, access_type, expires_at) VALUES (?, 'permanent', NULL)",
            (user_id,)
        )

    async def revoke_access(self, user_id: int) -> None:
        await self._db.execute("DELETE FROM concurrency_access WHERE user_id = ?", (user_id,))

    async def check_user_access(self, user_id: int) -> str:
        row = await self._db.fetchone(
            "SELECT access_type, expires_at FROM concurrency_access WHERE user_id = ?", 
            (user_id,)
        )
        if not row: return "none"
        
        access_type, expires_at = row
        if access_type == 'permanent': return "permanent"
        return "none"

    # --- BOOST LOGIC ---

    async def get_active_boost(self) -> Optional[Tuple[int, str, float]]:
        """Returns (user_id, username, expires_at) if someone is currently boosting."""
        row_user = await self._db.fetchone("SELECT value FROM meta WHERE key = 'active_boost_user_id'")
        if not row_user: return None
        user_id = int(row_user[0])
        
        row_name = await self._db.fetchone("SELECT value FROM meta WHERE key = 'active_boost_username'")
        username = row_name[0] if row_name else str(user_id)
        
        row_exp = await self._db.fetchone("SELECT value FROM meta WHERE key = 'active_boost_expires'")
        expires_at = float(row_exp[0]) if row_exp else 0.0
        
        return user_id, username, expires_at

    async def set_active_boost(self, user_id: int, username: str, expires_at: float) -> None:
        await self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('active_boost_user_id', ?)", (str(user_id),))
        await self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('active_boost_username', ?)", (username,))
        await self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('active_boost_expires', ?)", (str(expires_at),))

    async def clear_active_boost(self) -> None:
        await self._db.execute("DELETE FROM meta WHERE key IN ('active_boost_user_id', 'active_boost_username', 'active_boost_expires')")

    async def set_cooldown(self, user_id: int, expires_at: float) -> None:
        await self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f'boost_cooldown_{user_id}', str(expires_at)))

    async def get_cooldown(self, user_id: int) -> Optional[float]:
        row = await self._db.fetchone("SELECT value FROM meta WHERE key = ?", (f'boost_cooldown_{user_id}',))
        return float(row[0]) if row else None

    async def clear_cooldown(self, user_id: int) -> None:
        await self._db.execute("DELETE FROM meta WHERE key = ?", (f'boost_cooldown_{user_id}',))

    async def add_to_waitlist(self, user_id: int) -> None:
        await self._db.execute("INSERT OR IGNORE INTO boost_waitlist (user_id) VALUES (?)", (user_id,))

    async def get_and_clear_waitlist(self) -> List[int]:
        rows = await self._db.fetchall("SELECT user_id FROM boost_waitlist")
        if rows:
            await self._db.execute("DELETE FROM boost_waitlist")
        return [r[0] for r in rows]

    # --- BOOST COUNT STORAGE ---

    async def set_boost_count(self, user_id: int, count: int) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (f'boost_count_{user_id}', str(count))
        )

    async def get_boost_count(self, user_id: int) -> Optional[int]:
        row = await self._db.fetchone(
            "SELECT value FROM meta WHERE key = ?",
            (f'boost_count_{user_id}',)
        )
        return int(row[0]) if row else None

    async def clear_boost_count(self, user_id: int) -> None:
        await self._db.execute("DELETE FROM meta WHERE key = ?", (f'boost_count_{user_id}',))