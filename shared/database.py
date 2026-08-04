# File: shared/database.py
from __future__ import annotations

import aiosqlite
import asyncio
import logging

logger = logging.getLogger(__name__)

class Database:
    """Asynchronous SQLite database wrapper with Persistent Connection and WAL mode."""
    
    def __init__(self, db_path: str = "manga_bot.db"):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self.init_db()
        logger.info("Database connected successfully with WAL mode.")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            logger.info("Database connection closed.")

    async def init_db(self) -> None:
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS users_access (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL
            )
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER PRIMARY KEY,
                persona TEXT,
                mode TEXT,
                output_method TEXT,
                file_format TEXT
            )
        """)
        
        # Migration: Add session_mode column if it doesn't exist
        try:
            await self._conn.execute("ALTER TABLE settings ADD COLUMN session_mode TEXT")
            logger.info("Added 'session_mode' column to settings table.")
        except aiosqlite.OperationalError:
            pass # Column already exists

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_value TEXT PRIMARY KEY,
                user_id INTEGER
            )
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS concurrency_access (
                user_id INTEGER PRIMARY KEY,
                access_type TEXT NOT NULL,
                expires_at REAL
            )
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS boost_waitlist (
                user_id INTEGER PRIMARY KEY
            )
        """)
        
        # Indexes for performance
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_users_access_role ON users_access(role)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_concurrency_access_user_id ON concurrency_access(user_id)")
        
        await self._conn.commit()

    async def execute(self, query: str, params: tuple = ()) -> None:
        async with self._write_lock:
            await self._conn.execute(query, params)
            await self._conn.commit()

    async def fetchone(self, query: str, params: tuple = ()):
        async with self._conn.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        async with self._conn.execute(query, params) as cursor:
            return await cursor.fetchall()