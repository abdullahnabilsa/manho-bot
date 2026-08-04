# File: systems/delivery/senders/strategies/individual_session.py
from __future__ import annotations

import asyncio
import logging

from telegram import Bot, InputFile
from telegram.constants import ParseMode
from telegram.error import RetryAfter, BadRequest

from systems.delivery.renderers.telegram import TelegramRenderer
from systems.delivery.batch import BatchManager
from systems.access_control.user_settings import UserSettingsManager
from systems.job_orchestration.concurrency.manager import ConcurrencyManager
from systems.job_orchestration.queue import AsyncSingleWorkerQueue
from systems.translation_pipeline.registry import PersonaRegistry
from systems.translation_pipeline.models.page_job import PageJob
from utils.markdown_escaper import escape_markdown_v2

logger = logging.getLogger(__name__)

class IndividualSessionStrategy:
    def __init__(
        self,
        bot: Bot,
        batch: BatchManager,
        settings: UserSettingsManager,
        concurrency: ConcurrencyManager,
        personas: PersonaRegistry,
        queue: AsyncSingleWorkerQueue,
        renderer: TelegramRenderer
    ) -> None:
        self._bot = bot
        self._batch = batch
        self._settings = settings
        self._concurrency = concurrency
        self._personas = personas
        self._queue = queue
        self._renderer = renderer

    async def process(self, job: PageJob, handler) -> PageJob:
        is_active = await self._batch.is_session_active(job.user_id)
        if not is_active:
            logger.info(f"JobID={job.job_id} | User cancelled the session. Dropping queued job silently.")
            return job

        total_pages = await self._batch.add_page_data(job.user_id, job.page_data)
        queue_size = await self._queue.size()
        
        await self._send_stats_message(job, total_pages, queue_size)
        
        user_settings = await self._settings.get_user_settings(job.user_id)
        output_method = user_settings.get("output_method", "files_only")
        if output_method == "chat_and_files":
            output_method = "messages_and_files"
        fmt = user_settings.get("file_format", "docx")
        mode = user_settings.get("mode", "scene_split")
        
        if output_method in ["messages_only", "messages_and_files"]:
            temp_job = PageJob(user_id=job.user_id, chat_id=job.chat_id, page_data=job.page_data, file_name=job.file_name)
            msgs = await handler.paginate(temp_job, mode=mode)
            strings = [m for m in msgs]
            await self._renderer.render_messages(self._bot, temp_job, strings)
            
        if output_method in ["files_only", "messages_and_files"]:
            base_filename = job.file_name.split('.')[0] if job.file_name else f"image_{total_pages}"
            try:
                await self._concurrency.acquire_chat_send_lock(job.chat_id)
                if fmt in ["txt", "both"]:
                    file_io = await asyncio.to_thread(handler.generate_txt, [job.page_data])
                    try:
                        await self._bot.send_document(
                            chat_id=job.chat_id,
                            document=InputFile(file_io, filename=f"{base_filename}.txt")
                        )
                    except RetryAfter as e:
                        await asyncio.sleep(e.retry_after)
                        file_io.seek(0)
                        await self._bot.send_document(
                            chat_id=job.chat_id,
                            document=InputFile(file_io, filename=f"{base_filename}.txt")
                        )
                if fmt in ["docx", "both"]:
                    file_io = await asyncio.to_thread(handler.generate_docx, [job.page_data])
                    try:
                        await self._bot.send_document(
                            chat_id=job.chat_id,
                            document=InputFile(file_io, filename=f"{base_filename}.docx")
                        )
                    except RetryAfter as e:
                        await asyncio.sleep(e.retry_after)
                        file_io.seek(0)
                        await self._bot.send_document(
                            chat_id=job.chat_id,
                            document=InputFile(file_io, filename=f"{base_filename}.docx")
                        )
            finally:
                await self._concurrency.release_chat_send_lock(job.chat_id)
                
        return job

    async def _send_stats_message(self, job: PageJob, total_pages: int, queue_size: int) -> None:
        session_data = await self._batch.get_session_data(job.user_id)
        file_names = [escape_markdown_v2(pd.file_name) for pd in session_data if pd and pd.file_name]
        
        if len(file_names) > 25:
            start_index = len(file_names) - 10
            files_text = "_\\.\\.\\. عرض آخر 10 صور_\n" + "\n".join(
                [f"{i}\\. `{name}`" for i, name in enumerate(file_names[-10:], start=start_index + 1)]
            )
        else:
            files_text = "\n".join([f"{i}\\. `{name}`" for i, name in enumerate(file_names, start=1)])
            
        text = (
            f"✅ *تمت معالجة الصور بنجاح وتخزينها في الجلسة\\.*\n\n"
            f"📊 *إحصائيات الجلسة الحالية:*\n"
            f"• الصور المترجمة: `{total_pages}`\n"
            f"• الصور في الطابور: `{queue_size}`\n\n"
            f"📄 *الصور المجهزة:*\n{files_text}\n"
        )
        
        try:
            await self._bot.send_message(
                chat_id=job.chat_id, 
                text=text, 
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Failed to send individual stats message: {e}")

    async def compile_and_send(self, user_id: int, chat_id: int) -> None:
        await self._bot.send_message(
            chat_id=chat_id,
            text="✅ *اكتملت الجلسة بنجاح\\!*\nتم إرسال جميع ملفات الترجمة الفردية\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await self._batch.clear_session(user_id)
        await self._batch.clear_pending_compile(user_id)
        await self._batch.set_finalizing(user_id, False)