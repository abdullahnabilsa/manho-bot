# systems/job_orchestration/concurrency/manager.py
from __future__ import annotations
import asyncio
import logging
import time
from telegram import Bot
from telegram.constants import ParseMode

from systems.job_orchestration.concurrency.db_store import ConcurrencyDBStore
from systems.job_orchestration.concurrency.locks import LockManager
from shared.event_bus import EventBus

logger = logging.getLogger(__name__)

class ConcurrencyManager:
    """
    Facade that orchestrates DB checks and in-memory locks/semaphores.
    Communicates limit changes via EventBus to avoid circular dependencies.
    """
    def __init__(self, db_store: ConcurrencyDBStore, event_bus: EventBus) -> None:
        self._db_store = db_store
        self._locks = LockManager()
        self._event_bus = event_bus

    async def get_global_limit(self) -> int:
        return await self._db_store.get_global_limit()

    async def set_global_limit(self, limit: int) -> int:
        new_limit = await self._db_store.set_global_limit(limit)
        await self._event_bus.publish("concurrency.limit_changed", new_limit)
        return new_limit

    async def grant_permanent_access(self, user_id: int) -> None:
        await self._db_store.grant_permanent_access(user_id)

    async def revoke_access(self, user_id: int) -> None:
        await self._db_store.revoke_access(user_id)

    async def check_user_access(self, user_id: int) -> str:
        """Public access to user concurrency status."""
        perm = await self._db_store.check_user_access(user_id)
        if perm == "permanent": return "permanent"
        
        active = await self._db_store.get_active_boost()
        if active and active[0] == user_id and time.time() < active[2]:
            return "permanent"
        return "none"

    async def acquire_processing_slot(self, user_id: int) -> None:
        access = await self.check_user_access(user_id)
        if access == "none":
            sem = await self._locks.get_user_semaphore(user_id)
            await sem.acquire()
            logger.debug(f"User {user_id} acquired sequential processing slot.")
        else:
            # For permanent or boost users, acquire from their dynamic semaphore
            sem = await self._locks.get_user_semaphore(user_id)
            await sem.acquire()
            logger.debug(f"User {user_id} acquired parallel processing slot.")

    async def release_processing_slot(self, user_id: int) -> None:
        sem = await self._locks.get_user_semaphore(user_id)
        try:
            sem.release()
        except ValueError:
            # Semaphore was replaced (boost ended) — safe to ignore
            pass

    async def acquire_chat_send_lock(self, chat_id: int) -> None:
        chat_lock = await self._locks.get_chat_lock(chat_id)
        await chat_lock.acquire()

    async def release_chat_send_lock(self, chat_id: int) -> None:
        chat_lock = await self._locks.get_chat_lock(chat_id)
        if chat_lock.locked():
            chat_lock.release()

    async def acquire_tracker_lock(self, user_id: int) -> None:
        tracker_lock = await self._locks.get_tracker_lock(user_id)
        await tracker_lock.acquire()

    async def release_tracker_lock(self, user_id: int) -> None:
        tracker_lock = await self._locks.get_tracker_lock(user_id)
        if tracker_lock.locked():
            tracker_lock.release()

    # --- BOOST LOGIC ---

    async def request_boost(self, user_id: int, username: str, count: int = 2) -> dict:
        active = await self._db_store.get_active_boost()
        
        if active:
            active_user_id, active_username, expires_at = active
            if time.time() < expires_at:
                if active_user_id == user_id:
                    return {"status": "already_active", "expires_at": expires_at}
                
                await self._db_store.add_to_waitlist(user_id)
                return {
                    "status": "occupied", 
                    "active_user": active_username or str(active_user_id),
                    "expires_at": expires_at
                }
            else:
                # The previous boost expired, clean it up and set cooldown
                await self._db_store.clear_active_boost()
                await self._locks.reset_user_concurrency(active_user_id)
                await self._db_store.clear_boost_count(active_user_id)
                await self._db_store.set_cooldown(active_user_id, time.time() + 60)
        
        cooldown_until = await self._db_store.get_cooldown(user_id)
        if cooldown_until and time.time() < cooldown_until:
            return {"status": "cooldown", "expires_in": cooldown_until - time.time()}
        elif cooldown_until:
            await self._db_store.clear_cooldown(user_id)
            
        expires_at = time.time() + (10 * 60)
        await self._db_store.set_active_boost(user_id, username, expires_at)
        await self._db_store.set_boost_count(user_id, count)
        await self._locks.set_user_concurrency_limit(user_id, count)
        return {"status": "granted", "expires_at": expires_at, "count": count}

    async def deactivate_boost(self, user_id: int) -> bool:
        active = await self._db_store.get_active_boost()
        if active and active[0] == user_id:
            await self._db_store.clear_active_boost()
            await self._db_store.set_cooldown(user_id, time.time() + 60)
            await self._locks.reset_user_concurrency(user_id)
            await self._db_store.clear_boost_count(user_id)
            return True
        return False

    async def check_and_notify_waitlist(self, bot: Bot) -> None:
        waitlist = await self._db_store.get_and_clear_waitlist()
        for uid in waitlist:
            try:
                await bot.send_message(
                    chat_id=uid,
                    text="✅ *أصبحت المعالجة المتوازية متاحة الآن\\!*\nيمكنك استخدام الأمر `/boost` للحصول عليها\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as e:
                logger.warning(f"Failed to notify waitlist user {uid}: {e}")

    async def auto_expire_boost(self, user_id: int, bot: Bot) -> None:
        await asyncio.sleep(10 * 60 + 1)
        active = await self._db_store.get_active_boost()
        if active and active[0] == user_id:
            if time.time() >= active[2]:
                await self._db_store.clear_active_boost()
                await self._db_store.set_cooldown(user_id, time.time() + 60)
                await self._locks.reset_user_concurrency(user_id)
                await self._db_store.clear_boost_count(user_id)
                await self.check_and_notify_waitlist(bot)