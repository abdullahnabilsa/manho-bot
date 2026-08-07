# File: systems/delivery/pipeline.py
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, List

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
from systems.job_orchestration.worker import JobManager
from systems.job_orchestration.contracts import PipelineProtocol
from systems.translation_pipeline.models.page_job import PageJob, MessagePayload
from systems.glossary.manager import GlossaryManager
from utils.markdown_escaper import escape_markdown_v2

logger = logging.getLogger(__name__)

class DeliveryPipeline:
    """Facade implementing PipelineProtocol. Orchestrates AI → Render → Send."""
    
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
        await self._bot.send_chat_action(chat_id=job.chat_id, action=ChatAction.TYPING)
        
        is_session_active = await self._batch.is_session_active(job.user_id)
        if not is_session_active:
            logger.error(f"JobID={job.job_id} | Processing started without an active session. Aborting.")
            raise RuntimeError("Processing requires an active session.")

        if not job.image_bytes and job.image_file_id:
            try:
                tg_file = await self._bot.get_file(job.image_file_id)
                job.image_bytes = await tg_file.download_as_bytearray()
            except Exception as e:
                logger.error(f"JobID={job.job_id} | Failed to download image: {e}")
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

    async def send(self, job: PageJob) -> PageJob:
        await self._bot.send_chat_action(chat_id=job.chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        
        persona_name = await self._settings.get_persona(job.user_id)
        handler = self._personas.get_handler(persona_name)
        
        if not await self._batch.is_session_active(job.user_id):
            logger.info(f"JobID={job.job_id} | Session expired or cancelled before sending.")
            return job

        session_mode = await self._batch.get_session_mode(job.user_id)
        
        if session_mode == "individual":
            return await self._individual_strategy.process(job, handler)
        else:
            return await self._grouped_strategy.process(job, handler)

    async def compile_session(self, user_id: int, chat_id: int) -> None:
        session_mode = await self._batch.get_session_mode(user_id)
        if session_mode == "individual":
            await self._individual_strategy.compile_and_send(user_id, chat_id)
        else:
            await self._grouped_strategy.compile_and_send(user_id, chat_id)

    async def flush_pending_to_queue(self, user_id: int, chat_id: int) -> None:
        """Phase 2: Flushes cached pending files into the JobManager queue."""
        pending_files = await self._batch.get_pending_files(user_id)
        if not pending_files:
            logger.warning(f"Flush called for UserID={user_id} but no pending files found.")
            return
            
        await self._batch.clear_pending_files(user_id)
        
        for file_id, file_name, photo_msg_id in pending_files:
            job = PageJob(
                user_id=user_id, 
                chat_id=chat_id, 
                image_file_id=file_id, 
                file_name=file_name,
                photo_message_id=photo_msg_id
            )
            await self._jobs.submit_job(job)
            await self._batch.increment_received_count(user_id)
            
        logger.info(f"UserID={user_id} | Flushed {len(pending_files)} pending files to queue.")