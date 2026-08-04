# File: systems/delivery/senders/strategies/grouped_session.py
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

class GroupedSessionStrategy:
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
        is_pending = await self._batch.is_pending_compile(job.user_id)
        queue_size = await self._queue.size()
        total_received = await self._batch.get_received_count(job.user_id)
        
        processing_count = total_received - total_pages - queue_size
        if processing_count < 0:
            processing_count = 0
        
        await self._update_session_tracker(job, total_pages, queue_size, processing_count, total_received, is_pending)
        
        if is_pending and queue_size == 0 and processing_count == 0:
            if await self._batch.try_acquire_compile_lock(job.user_id):
                await self.compile_and_send(job.user_id, job.chat_id)
            
        return job

    async def _update_session_tracker(
        self, job: PageJob, total_pages: int, queue_size: int, processing_count: int, total_received: int, is_pending: bool
    ) -> None:
        await self._concurrency.acquire_tracker_lock(job.user_id)
        try:
            tracker_id = await self._batch.get_tracker(job.user_id)
            session_data = await self._batch.get_session_data(job.user_id)
            
            file_names = [escape_markdown_v2(pd.file_name) for pd in session_data if pd and pd.file_name]
            
            if len(file_names) > 25:
                start_index = len(file_names) - 10
                files_text = "_\\.\\.\\. عرض آخر 10 صور_\n" + "\n".join(
                    [f"{i}\\. `{name}`" for i, name in enumerate(file_names[-10:], start=start_index + 1)]
                )
            else:
                files_text = "\n".join([f"{i}\\. `{name}`" for i, name in enumerate(file_names, start=1)])
            
            if is_pending:
                if queue_size > 0 or processing_count > 0:
                    text = (
                        f"⏳ *معالجة الصور المتبقية للجلسة...*\n\n"
                        f"📊 *إحصائيات الجلسة الحالية:*\n"
                        f"• إجمالي الصور المرسلة: `{total_received}`\n"
                        f"• تمت ترجمتها: `{total_pages}`\n"
                        f"• قيد المعالجة الآن: `{processing_count}`\n"
                        f"• في الطابور: `{queue_size}`\n\n"
                        f"📄 *الصور المجهزة:*\n{files_text}\n\n"
                        f"_تم استلام اسم الملف\\. جاري معالجة الباقي تلقائياً، يرجى الانتظار..._"
                    )
                else:
                    text = "📦 *اكتملت معالجة جميع الصور\\!*\nجاري تجميع الملفات النهائية وإرسالها\\.\\.\\."
            else:
                text = (
                    f"✅ *تمت معالجة الصور بنجاح وتخزينها في الجلسة\\.*\n\n"
                    f"📊 *إحصائيات الجلسة الحالية:*\n"
                    f"• إجمالي الصور المرسلة: `{total_received}`\n"
                    f"• تمت ترجمتها: `{total_pages}`\n"
                    f"• قيد المعالجة الآن: `{processing_count}`\n"
                    f"• في الطابور: `{queue_size}`\n\n"
                    f"📄 *الصور المجهزة:*\n{files_text}\n\n"
                    f"_يمكنك متابعة الإرسال، أو اضغط 🔴 إنهاء الجلسة لتجميع الملفات\\._"
                )
                
            if tracker_id:
                try:
                    await self._bot.edit_message_text(
                        chat_id=job.chat_id, message_id=tracker_id,
                        text=text, parse_mode=ParseMode.MARKDOWN_V2
                    )
                    return
                except BadRequest as e:
                    err_str = str(e).lower()
                    if "message is not modified" in err_str:
                        return
                    if "message to edit not found" in err_str or "message can't be edited" in err_str:
                        await self._batch.set_tracker(job.user_id, None)
                        tracker_id = None
                    else:
                        return
                except RetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    try:
                        await self._bot.edit_message_text(
                            chat_id=job.chat_id, message_id=tracker_id,
                            text=text, parse_mode=ParseMode.MARKDOWN_V2
                        )
                    except Exception:
                        pass
                    return
                except Exception:
                    return
                
            if not tracker_id:
                try:
                    msg = await self._bot.send_message(
                        chat_id=job.chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2
                    )
                    await self._batch.set_tracker(job.user_id, msg.message_id)
                except Exception as e:
                    logger.error(f"Failed to create new tracker: {e}")
        finally:
            await self._concurrency.release_tracker_lock(job.user_id)

    async def compile_and_send(self, user_id: int, chat_id: int) -> None:
        session_data = await self._batch.get_session_data(user_id)
        if not session_data:
            await self._batch.set_finalizing(user_id, False)
            return

        custom_name = await self._batch.get_custom_filename(user_id)
        base_filename = custom_name if custom_name else "manga_session"
        
        user_settings = await self._settings.get_user_settings(user_id)
        output_method = user_settings.get("output_method", "files_only")
        if output_method == "chat_and_files":
            output_method = "messages_and_files"
        fmt = user_settings.get("file_format", "docx")
        mode = user_settings.get("mode", "scene_split")
        
        persona_name = await self._batch.get_session_persona(user_id)
        handler = self._personas.get_handler(persona_name)

        try:
            if output_method == "messages_only":
                for pd in session_data:
                    temp_job = PageJob(user_id=user_id, chat_id=chat_id, page_data=pd, file_name=pd.file_name)
                    msgs = await handler.paginate(temp_job, mode=mode)
                    for msg_text in msgs:
                        try:
                            await self._bot.send_message(
                                chat_id=chat_id, text=msg_text,
                                parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
                            )
                            await asyncio.sleep(0.3)
                        except RetryAfter as e:
                            await asyncio.sleep(e.retry_after)
                            try:
                                await self._bot.send_message(
                                    chat_id=chat_id, text=msg_text,
                                    parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
                                )
                            except Exception:
                                pass
            else:
                await self._concurrency.acquire_chat_send_lock(chat_id)
                try:
                    if fmt in ["txt", "both"]:
                        file_io = await asyncio.to_thread(handler.generate_txt, session_data)
                        try:
                            await self._bot.send_document(
                                chat_id=chat_id,
                                document=InputFile(file_io, filename=f"{base_filename}.txt")
                            )
                        except RetryAfter as e:
                            await asyncio.sleep(e.retry_after)
                            file_io.seek(0)
                            await self._bot.send_document(
                                chat_id=chat_id,
                                document=InputFile(file_io, filename=f"{base_filename}.txt")
                            )

                    if fmt in ["docx", "both"]:
                        file_io = await asyncio.to_thread(handler.generate_docx, session_data)
                        try:
                            await self._bot.send_document(
                                chat_id=chat_id,
                                document=InputFile(file_io, filename=f"{base_filename}.docx")
                            )
                        except RetryAfter as e:
                            await asyncio.sleep(e.retry_after)
                            file_io.seek(0)
                            await self._bot.send_document(
                                chat_id=chat_id,
                                document=InputFile(file_io, filename=f"{base_filename}.docx")
                            )
                finally:
                    await self._concurrency.release_chat_send_lock(chat_id)
                    
            await self._bot.send_message(
                chat_id=chat_id,
                text="✅ *اكتملت الجلسة\\!*\nتم تجهيز الملفات وإرسالها بنجاح\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
            prompt_msg_id = await self._batch.get_prompt_message_id(user_id)
            if prompt_msg_id:
                try:
                    await self._bot.delete_message(chat_id=chat_id, message_id=prompt_msg_id)
                except Exception:
                    pass
                
        except Exception as e:
            logger.error(f"Failed to process deferred compile: {e}")
            await self._bot.send_message(
                chat_id=chat_id,
                text="❌ *فشل التجميع\\.*\nحدث خطأ أثناء دمج ملفات الجلسة\\. يرجى المحاولة لاحقاً\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
        await self._batch.clear_session(user_id)
        await self._batch.clear_pending_compile(user_id)
        await self._batch.set_finalizing(user_id, False)