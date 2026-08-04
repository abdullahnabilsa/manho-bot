# File: systems/access_control/user_settings.py
from __future__ import annotations

import logging
from typing import Dict, Any
from shared.database import Database

logger = logging.getLogger(__name__)

class UserSettingsManager:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._cache: Dict[int, Dict[str, Any]] = {}

    async def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        if user_id in self._cache:
            return self._cache[user_id]

        row = await self._db.fetchone("SELECT persona, mode, output_method, file_format, session_mode FROM settings WHERE user_id = ?", (user_id,))
        
        if row:
            settings = {
                "persona": row[0] or "Default Translator",
                "mode": row[1] or "scene_split",
                "output_method": row[2] or "files_only",
                "file_format": row[3] or "docx",
                "session_mode": row[4] or "grouped"
            }
        else:
            settings = {
                "persona": "Default Translator",
                "mode": "scene_split",
                "output_method": "files_only",
                "file_format": "docx",
                "session_mode": "grouped"
            }
        
        self._cache[user_id] = settings
        return settings

    async def get_persona(self, user_id: int) -> str:
        return (await self.get_user_settings(user_id)).get("persona")

    async def set_persona(self, user_id: int, persona_name: str) -> None:
        await self._db.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
        await self._db.execute("UPDATE settings SET persona = ? WHERE user_id = ?", (persona_name, user_id))
        if user_id in self._cache:
            self._cache[user_id]["persona"] = persona_name

    async def get_delivery_mode(self, user_id: int) -> str:
        return (await self.get_user_settings(user_id)).get("mode", "scene_split")

    async def set_delivery_mode(self, user_id: int, mode: str) -> None:
        await self._db.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
        await self._db.execute("UPDATE settings SET mode = ? WHERE user_id = ?", (mode, user_id))
        if user_id in self._cache:
            self._cache[user_id]["mode"] = mode

    async def get_output_method(self, user_id: int) -> str:
        return (await self.get_user_settings(user_id)).get("output_method", "files_only")

    async def set_output_method(self, user_id: int, method: str) -> None:
        await self._db.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
        await self._db.execute("UPDATE settings SET output_method = ? WHERE user_id = ?", (method, user_id))
        if user_id in self._cache:
            self._cache[user_id]["output_method"] = method

    async def get_file_format(self, user_id: int) -> str:
        return (await self.get_user_settings(user_id)).get("file_format", "docx")

    async def set_file_format(self, user_id: int, fmt: str) -> None:
        await self._db.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
        await self._db.execute("UPDATE settings SET file_format = ? WHERE user_id = ?", (fmt, user_id))
        if user_id in self._cache:
            self._cache[user_id]["file_format"] = fmt

    async def get_session_mode(self, user_id: int) -> str:
        return (await self.get_user_settings(user_id)).get("session_mode", "grouped")

    async def set_session_mode(self, user_id: int, session_mode: str) -> None:
        await self._db.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
        await self._db.execute("UPDATE settings SET session_mode = ? WHERE user_id = ?", (session_mode, user_id))
        if user_id in self._cache:
            self._cache[user_id]["session_mode"] = session_mode