# systems/access_control/api_key_manager.py
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional
from shared.database import Database

logger = logging.getLogger(__name__)

class APIKeyManager:
    """Manages public and user-specific API keys securely via SQLite with Round-Robin."""
    
    def __init__(self, db: Database) -> None:
        self._db = db
        self._public_key_index = 0
        self._rotation_lock = asyncio.Lock()

    async def add_public_key(self, key: str) -> bool:
        existing = await self._db.fetchone("SELECT 1 FROM api_keys WHERE key_value = ?", (key,))
        if existing: return False
        await self._db.execute("INSERT INTO api_keys (key_value, user_id) VALUES (?, NULL)", (key,))
        return True

    async def remove_public_key(self, key: str) -> bool:
        existing = await self._db.fetchone("SELECT 1 FROM api_keys WHERE key_value = ? AND user_id IS NULL", (key,))
        if not existing: return False
        await self._db.execute("DELETE FROM api_keys WHERE key_value = ? AND user_id IS NULL", (key,))
        return True

    async def get_public_keys(self) -> List[str]:
        rows = await self._db.fetchall("SELECT key_value FROM api_keys WHERE user_id IS NULL")
        return [row[0] for row in rows]

    async def set_user_key(self, user_id: int, key: str) -> None:
        await self._db.execute("INSERT OR REPLACE INTO api_keys (key_value, user_id) VALUES (?, ?)", (key, user_id))

    async def remove_user_key(self, user_id: int) -> bool:
        existing = await self._db.fetchone("SELECT key_value FROM api_keys WHERE user_id = ?", (user_id,))
        if not existing: return False
        await self._db.execute("DELETE FROM api_keys WHERE user_id = ?", (user_id,))
        return True

    async def get_user_key(self, user_id: int) -> Optional[str]:
        row = await self._db.fetchone("SELECT key_value FROM api_keys WHERE user_id = ?", (user_id,))
        return row[0] if row else None

    async def get_keys_for_user(self, user_id: int) -> List[str]:
        user_key = await self.get_user_key(user_id)
        if user_key:
            return [user_key]
            
        public_keys = await self.get_public_keys()
        if not public_keys:
            return []
            
        async with self._rotation_lock:
            start_index = self._public_key_index % len(public_keys)
            self._public_key_index += 1
            
        rotated_keys = public_keys[start_index:] + public_keys[:start_index]
        return rotated_keys