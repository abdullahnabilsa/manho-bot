# systems/delivery/pipeline.py
from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import Callable, List, Optional, Tuple

from telegram import Bot
from telegram.constants import ChatAction, ParseMode

from config.settings import Settings
from systems.ai_engine.base import BaseAIProvider
from systems.translation_pipeline.registry import PersonaRegistry
from systems.access_control.api_key_manager import APIKeyManager
from systems.access_control.user_settings import UserSettingsManager
from systems.delivery.batch import BatchManager
from systems.delivery.senders.strategies.grouped_session import GroupedSessionStrategy
from systems.delivery.senders.strategies.individual_session import IndividualSessionStrategy
from systems.delivery.utils import safe_edit_or_send
from systems.job_orchestration.queue import AsyncSingleWorkerQueue
from systems.job_orchestration.worker import JobManager, JobSubmissionResult
from systems.job_orchestration.contracts import PipelineProtocol
from systems.translation_pipeline.models.page_job import PageJob, MessagePayload
from systems.glossary.manager import GlossaryManager
from utils.markdown_escaper import escape_markdown_v2

logger = logging.getLogger(__name__)

class FlushResult(Enum):
    ALLOWED = 1
    WAITING = 2
    EMPTY = 3
    QUEUE_FULL = 4

class DeliveryPipeline:
    """Facade implementing PipelineProtocol. Orchestrates AI → Render → Deliver."""
    
    def __init__(
        self,
        bot: Bot,
        ai_provider: BaseAIProvider,
        persona_registry: PersonaRegistry,
        api_key_manager: APIKeyManager,
        settings_manager: UserSettingsManager,
        batch_manager: BatchManager,
        grouped_strategy: GroupedSessionStrategy,
        individual_strategy: IndividualSessionStrategy,
        image_optimizer: Callable[[bytes], bytes],
        queue_manager: AsyncSingleWorkerQueue,
        glossary_manager: GlossaryManager,
        job_manager: JobManager
    ) -> None:
        self._bot = bot
        self._ai = ai_provider
        self._personas = persona_registry
        self._api_keys = api_key_manager
        self._settings = settings_manager
        self._batch = batch_manager
        self._grouped_strategy = grouped_strategy
        self._individual_strategy = individual_strategy
        self._image_optimizer = image_optimizer
        self._queue = queue_manager
        self._glossary = glossary_manager
        self._jobs = job_manager
        self._env_settings = Settings()

    async def process(self, job: PageJob) -> PageJob:
        is_session_active = await self._batch.is_session_active(job.user_id)
        if not is_session_active:
            raise RuntimeError("Processing requires an active session.")

        if not job.image_bytes and job.image_file_id:
            try:
                tg_file = await asyncio.wait_for(self._bot.get_file(job.image_file_id), timeout=30.0)
                job.image_bytes = await asyncio.wait_for(tg_file.download_as_bytearray(), timeout=30.0)
            except asyncio.TimeoutError:
                raise RuntimeError(f"Telegram download timeout for JobID={job.job_id}")
            except Exception as e:
                raise RuntimeError(f"Failed to download image file: {e}")

        if job.image_bytes:
            job.image_bytes = self._image_optimizer(job.image_bytes)

        persona_name = await self._settings.get_persona(job.user_id)
        if not persona_name or persona_name not in self._personas.get_available_personas():
            persona_name = "Default Translator"
            
        handler = self._personas.get_handler(persona_name)
        prompt_text = handler.prompt
        
        user_settings = await self._settings.get_user_settings(job.user_id)
        use_glossary = user_settings.get("use_glossary", "false") == "true"
        
        if use_glossary:
            glossary_data = await self._glossary.load_glossary()
            if glossary_data:
                glossary_str = json.dumps(glossary_data, ensure_ascii=False, indent=2)
                prompt_text += f"\n\n# GLOSSARY\nYou MUST strictly use the following dictionary for translating the corresponding terms. If a word from the image exists in this glossary, you must use its exact provided translation:\n{glossary_str}\n"
        
        api_keys = await self._api_keys.get_keys_for_user(job.user_id)
        if not api_keys:
            env_key = self._env_settings.ai_api_key
            if env_key:
                api_keys = [env_key]
            else:
                raise RuntimeError("No API keys available for the user and no fallback key in .env")
        
        raw_json = await self._ai.extract_raw_json(
            image_bytes=job.image_bytes,
            job_id=job.job_id,
            prompt_text=prompt_text,
            api_keys=api_keys
        )
        
        # Memory Optimization: Free RAM immediately after AI processing
        job.image_bytes = None
        job.image_file_id = None
        
        job = await handler.validate_and_update_job(job, raw_json)
        if job.page_data:
            job.page_data.file_name = job.file_name
        return job

    async def render(self, job: PageJob) -> PageJob:
        persona_name = await self._settings.get_persona(job.user_id)
        handler = self._personas.get_handler(persona_name)
        
        user_settings = await self._settings.get_user_settings(job.user_id)
        mode = user_settings.get("mode", "scene_split")
        
        messages: List[str] = await handler.paginate(job, mode=mode)
        job.message_payloads = [
            MessagePayload(page_index=i, total_pages=len(messages), text=msg)
            for i, msg in enumerate(messages)
        ]
        return job

    async def deliver(self, job: PageJob) -> PageJob:
        if not await self._batch.is_session_active(job.user_id):
            logger.info(f"JobID={job.job_id} | Session expired or cancelled before delivery.")
            return job

        session_mode = await self._batch.get_session_mode(job.user_id)
        
        if session_mode == "individual":
            return await self._individual_strategy.process(job, handler=None)
        else:
            return await self._grouped_strategy.process(job, handler=None)

    async def compile_session(self, user_id: int, chat_id: int) -> None:
        session_mode = await self._batch.get_session_mode(user_id)
        if session_mode == "individual":
            await self._individual_strategy.compile_and_send(user_id, chat_id)
        else:
            await self._grouped_strategy.compile_and_send(user_id, chat_id)

    async def flush_pending_to_queue(self, user_id: int, chat_id: int) -> FlushResult:
        pending_files = await self._batch.get_pending_files(user_id)
        if not pending_files:
            return FlushResult.EMPTY

        is_allowed = await self._jobs.request_processing(user_id, chat_id, len(pending_files))
        if not is_allowed:
            return FlushResult.WAITING
            
        await self._batch.clear_pending_files(user_id)
        
        for file_id, file_name, photo_msg_id in pending_files:
            job = PageJob(
                user_id=user_id, 
                chat_id=chat_id, 
                image_file_id=file_id, 
                file_name=file_name,
                photo_message_id=photo_msg_id
            )
            result = await self._jobs.submit_job(job)
            if result == JobSubmissionResult.QUEUE_FULL:
                return FlushResult.QUEUE_FULL
            await self._batch.increment_received_count(user_id)
            
        return FlushResult.ALLOWED

    async def activate_next_user(self) -> None:
        next_user = await self._jobs.release_active_user()
        if next_user:
            next_user_id, next_chat_id = next_user
            await self.activate_waiting_user(next_user_id, next_chat_id)

    async def activate_waiting_user(self, user_id: int, chat_id: int) -> None:
        waiting_msg_id = await self._batch.get_waiting_message_id(user_id)
        if waiting_msg_id:
            try:
                await self._bot.delete_message(chat_id=chat_id, message_id=waiting_msg_id)
            except Exception:
                pass
            await self._batch.clear_waiting_state(user_id)
        
        result = await self.flush_pending_to_queue(user_id, chat_id)
        if result == FlushResult.ALLOWED:
            total_received = await self._batch.get_received_count(user_id)
            text = (
                "⏳ <b>جاري ترجمة الصور وتجميع الملف...</b>\n\n"
                "📊 <b>إحصائيات الجلسة الحالية:</b>\n"
                f"• إجمالي الصور: <code>{total_received}</code>\n"
                "• تمت ترجمتها: <code>0</code>\n"
                "• قيد المعالجة الآن: <code>0</code>\n"
                "• في الطابور: <code>0</code>\n\n"
                "<i>يعمل النظام بـ 5 عمال متوازيين، يرجى الانتظار حتى يتم تجميع كل الملفات.</i>"
            )
            try:
                msg = await self._bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
                await self._batch.set_tracker(user_id, msg.message_id)
                await self._batch.force_update_tracker(user_id)
            except Exception as e:
                logger.error(f"Failed to create tracker for waiting user: {e}")
        elif result == FlushResult.QUEUE_FULL:
            try:
                await self._bot.send_message(chat_id=chat_id, text="🚨 الضغط على النظام مرتفع جداً. يرجى المحاولة لاحقاً.")
            except Exception:
                pass

    async def finalize_session_and_advance(self, user_id: int, chat_id: int) -> None:
        try:
            await self._batch.clear_session(user_id)
            await self._batch.clear_pending_compile(user_id)
            await self._batch.set_finalizing(user_id, False)
        except Exception as e:
            logger.error(f"Failed to clear session state for user {user_id}: {e}")
            
        try:
            next_user = await self._jobs.release_active_user()
            if next_user:
                next_user_id, next_chat_id = next_user
                await self.activate_waiting_user(next_user_id, next_chat_id)
        except Exception as e:
            logger.error(f"Failed to activate next user during handoff: {e}")