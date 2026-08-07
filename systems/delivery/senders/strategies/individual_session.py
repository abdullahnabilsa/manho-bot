# File: systems/delivery/senders/strategies/individual_session.py
from __future__ import annotations

import asyncio
import logging
import time as _time

from telegram import Bot, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import RetryAfter, BadRequest

from systems.delivery.renderers.telegram import TelegramRenderer
from systems.delivery.batch import BatchManager
from systems.access_control.user_settings import UserSettingsManager
from systems.job_orchestration.queue import AsyncSingleWorkerQueue
from systems.translation_pipeline.registry import PersonaRegistry
from systems.translation_pipeline.models.page_job import PageJob
from utils.markdown_escaper import escape_markdown_v2, escape_html

logger = logging.getLogger(__name__)

def _generate_progress_bar(processed: int, total: int) -> str:
    if total == 0:
        return "[░░░░░░░░░░] 0%"
    percentage = min(100, int((processed / total) * 100))
    filled_blocks = int(percentage / 10)
    empty_blocks = 10 - filled_blocks
    return f"[{'█' * filled_blocks}{'░' * empty_blocks}] {percentage}%"

class IndividualSessionStrategy:
    def __init__(
        self,
        bot: Bot,
        batch: BatchManager,
        settings: UserSettingsManager,
        personas: PersonaRegistry,
        queue: AsyncSingleWorkerQueue,
        renderer: TelegramRenderer
    ) -> None:
        self._bot = bot
        self._batch = batch
        self._settings = settings
        self._personas = personas
        self._queue = queue
        self._renderer = renderer

    async def process(self, job: PageJob, handler) -> PageJob:
        is_active = await self._batch.is_session_active(job.user_id)
        if not is_active:
            logger.info(f"JobID={job.job_id} | User cancelled the session. Dropping queued job silently.")
            return job

        processed_pages = await self._batch.add_page_data(job.user_id, job.page_data)
        queue_size = await self._queue.size()
        total_received = await self._batch.get_received_count(job.user_id)
        processing_count = total_received - processed_pages - queue_size
        if processing_count < 0:
            processing_count = 0
            
        await self._update_session_tracker(job, processed_pages, queue_size, processing_count, total_received)
        
        user_settings = await self._settings.get_user_settings(job.user_id)
        output_method = user_settings.get("output_method", "files_only")
        if output_method == "chat_and_files":
            output_method = "messages_and_files"
        fmt = user_settings.get("file_format", "docx")
        mode = user_settings.get("mode", "scene_split")
        
        note = await self._batch.get_session_note(job.user_id) or None
        
        if output_method in ["messages_only", "messages_and_files"]:
            temp_job = PageJob(user_id=job.user_id, chat_id=job.chat_id, page_data=job.page_data, file_name=job.file_name)
            msgs = await handler.paginate(temp_job, mode=mode)
            strings = [m for m in msgs]
            await self._renderer.render_messages(self._bot, temp_job, strings)
            
        if output_method in ["files_only", "messages_and_files"]:
            base_filename = job.file_name.split('.')[0] if job.file_name else f"image_{processed_pages}"
            try:
                await self._batch.acquire_chat_send_lock(job.chat_id)
                if fmt in ["txt", "both"]:
                    file_io = await asyncio.to_thread(handler.generate_txt, [job.page_data], note)
                    try:
                        await self._bot.send_document(
                            chat_id=job.chat_id,
                            document=InputFile(file_io, filename=f"{base_filename}.txt"),
                            reply_to_message_id=job.photo_message_id
                        )
                        await asyncio.sleep(0.5)  # Mandatory delay shield
                    except RetryAfter as e:
                        await asyncio.sleep(e.retry_after)
                        file_io.seek(0)
                        await self._bot.send_document(
                            chat_id=job.chat_id,
                            document=InputFile(file_io, filename=f"{base_filename}.txt"),
                            reply_to_message_id=job.photo_message_id
                        )
                if fmt in ["docx", "both"]:
                    file_io = await asyncio.to_thread(handler.generate_docx, [job.page_data], note)
                    try:
                        await self._bot.send_document(
                            chat_id=job.chat_id,
                            document=InputFile(file_io, filename=f"{base_filename}.docx"),
                            reply_to_message_id=job.photo_message_id
                        )
                        await asyncio.sleep(0.5)  # Mandatory delay shield
                    except RetryAfter as e:
                        await asyncio.sleep(e.retry_after)
                        file_io.seek(0)
                        await self._bot.send_document(
                            chat_id=job.chat_id,
                            document=InputFile(file_io, filename=f"{base_filename}.docx"),
                            reply_to_message_id=job.photo_message_id
                        )
            finally:
                await self._batch.release_chat_send_lock(job.chat_id)

        # Final state detection
        is_pending = await self._batch.is_pending_compile(job.user_id)
        if is_pending and queue_size == 0 and processing_count == 0:
            if await self._batch.try_acquire_compile_lock(job.user_id):
                await self.compile_and_send(job.user_id, job.chat_id)
                
        return job

    async def _update_session_tracker(self, job: PageJob, processed_pages: int, queue_size: int, processing_count: int, total_received: int) -> None:
        is_final_state = (queue_size == 0 and processing_count == 0)
        
        if is_final_state:
            await self._batch.force_update_tracker(job.user_id)
            
        if not await self._batch.can_update_tracker(job.user_id):
            return
            
        await self._batch.acquire_tracker_lock(job.user_id)
        try:
            tracker_id = await self._batch.get_tracker(job.user_id)
            start_time = await self._batch.get_session_start_time(job.user_id)
            
            elapsed_secs = int(_time.time() - start_time) if start_time else 0
            hours, rem = divmod(elapsed_secs, 3600)
            mins, secs = divmod(rem, 60)
            elapsed_time = f"{hours:02d}:{mins:02d}:{secs:02d}"
            
            progress_bar = _generate_progress_bar(processed_pages, total_received)
            
            note = await self._batch.get_session_note(job.user_id)
            note_block = f"📝 <b>الملاحظة:</b>\n<i>{escape_html(note)}</i>\n\n" if note else ""
            
            text = (
                f"{progress_bar}\n\n"
                f"⏳ <b>جاري ترجمة الصور وإرسالها فردياً...</b>\n\n"
                f"📊 <b>إحصائيات الجلسة الحالية:</b>\n"
                f"• إجمالي الصور: <code>{total_received}</code>\n"
                f"• تمت ترجمتها: <code>{processed_pages}</code>\n"
                f"• قيد المعالجة الآن: <code>{processing_count}</code>\n"
                f"• في الطابور: <code>{queue_size}</code>\n"
                f"⏱ <b>الوقت المنقضي:</b> <code>{elapsed_time}</code>\n\n"
                f"{note_block}"
                f"<i>وضع التجميع الفردي: يتم إرسال ملف الترجمة فور انتهاء كل صورة.</i>"
            )
                
            if tracker_id:
                try:
                    await self._bot.edit_message_text(
                        chat_id=job.chat_id, message_id=tracker_id,
                        text=text, parse_mode=ParseMode.HTML
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
                            text=text, parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
                    return
                except Exception:
                    return
                
            if not tracker_id:
                try:
                    msg = await self._bot.send_message(
                        chat_id=job.chat_id, text=text, parse_mode=ParseMode.HTML
                    )
                    await self._batch.set_tracker(job.user_id, msg.message_id)
                except Exception as e:
                    logger.error(f"Failed to create new individual tracker: {e}")
        finally:
            await self._batch.release_tracker_lock(job.user_id)

    async def compile_and_send(self, user_id: int, chat_id: int) -> None:
        tracker_id = await self._batch.get_tracker(user_id)
        total_images = await self._batch.get_received_count(user_id)
        start_time = await self._batch.get_session_start_time(user_id)
        elapsed_secs = int(_time.time() - start_time) if start_time else 0
        hours, rem = divmod(elapsed_secs, 3600)
        mins, secs = divmod(rem, 60)
        elapsed_time = f"{hours:02d}:{mins:02d}:{secs:02d}"
        
        note = await self._batch.get_session_note(user_id)
        
        log_text = (
            f"✅ <b>اكتملت الجلسة الفردية</b>\n"
            f"🖼️ <b>عدد الصور:</b> <code>{total_images}</code>\n"
            f"⏱️ <b>الوقت المستغرق:</b> <code>{elapsed_time}</code>\n"
        )
        if note:
            log_text += f"📝 <b>الملاحظة:</b>\n<i>{escape_html(note)}</i>\n"
            
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ حذف الصور الأصلية", callback_data="cleanup_photos")]])
        
        if tracker_id:
            try:
                await self._bot.edit_message_text(
                    chat_id=chat_id, message_id=tracker_id,
                    text=log_text, parse_mode=ParseMode.HTML, reply_markup=keyboard
                )
            except Exception:
                pass
            await self._batch.set_tracker(user_id, None)
        else:
            await self._bot.send_message(
                chat_id=chat_id, text=log_text, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
                
        await self._batch.clear_session(user_id)
        await self._batch.clear_pending_compile(user_id)
        await self._batch.set_finalizing(user_id, False)