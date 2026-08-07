# File: systems/delivery/senders/strategies/grouped_session.py
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

class GroupedSessionStrategy:
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
        is_pending = await self._batch.is_pending_compile(job.user_id)
        queue_size = await self._queue.size()
        total_received = await self._batch.get_received_count(job.user_id)
        
        processing_count = total_received - processed_pages - queue_size
        if processing_count < 0:
            processing_count = 0
        
        await self._update_session_tracker(job, processed_pages, queue_size, processing_count, total_received, is_pending)
        
        if is_pending and queue_size == 0 and processing_count == 0:
            if await self._batch.try_acquire_compile_lock(job.user_id):
                try:
                    await self._bot.send_message(
                        chat_id=job.chat_id,
                        text="📦 <b>اكتملت معالجة جميع الصور!</b>\nجاري تجميع الملفات النهائية وإرسالها...",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass
                await self.compile_and_send(job.user_id, job.chat_id)
            
        return job

    async def _update_session_tracker(
        self, job: PageJob, processed_pages: int, queue_size: int, processing_count: int, total_received: int, is_pending: bool
    ) -> None:
        is_final_state = (queue_size == 0 and processing_count == 0)
        
        if is_final_state:
            await self._batch.force_update_tracker(job.user_id)
            
        if not await self._batch.can_update_tracker(job.user_id):
            return
            
        await self._batch.acquire_tracker_lock(job.user_id)
        try:
            tracker_id = await self._batch.get_tracker(job.user_id)
            session_data = await self._batch.get_session_data(job.user_id)
            start_time = await self._batch.get_session_start_time(job.user_id)
            
            elapsed_secs = int(_time.time() - start_time) if start_time else 0
            hours, rem = divmod(elapsed_secs, 3600)
            mins, secs = divmod(rem, 60)
            elapsed_time = f"{hours:02d}:{mins:02d}:{secs:02d}"
            
            file_names = [escape_html(pd.file_name) for pd in session_data if pd and pd.file_name]
            
            if len(file_names) > 25:
                start_index = len(file_names) - 10
                files_text = "… عرض آخر 10 صور\n" + "\n".join(
                    [f"{i}. {name}" for i, name in enumerate(file_names[-10:], start=start_index + 1)]
                )
            else:
                files_text = "\n".join([f"{i}. {name}" for i, name in enumerate(file_names, start=1)])
                
            files_block = f"<blockquote expandable>📄 <b>الصور المجهزة:</b>\n{files_text}</blockquote>"
            
            progress_bar = _generate_progress_bar(processed_pages, total_received)
            
            note = await self._batch.get_session_note(job.user_id)
            note_block = f"📝 <b>الملاحظة:</b>\n<i>{escape_html(note)}</i>\n\n" if note else ""
            
            if is_pending:
                status_text = "⏳ <b>جاري ترجمة الصور وتجميع الملف...</b>"
                if is_final_state:
                    status_text = "✅ <b>تمت معالجة جميع الصور بنجاح!</b>"
                    
                text = (
                    f"{progress_bar}\n\n"
                    f"{status_text}\n\n"
                    f"📊 <b>إحصائيات الجلسة الحالية:</b>\n"
                    f"• إجمالي الصور: <code>{total_received}</code>\n"
                    f"• تمت ترجمتها: <code>{processed_pages}</code>\n"
                    f"• قيد المعالجة الآن: <code>{processing_count}</code>\n"
                    f"• في الطابور: <code>{queue_size}</code>\n"
                    f"⏱ <b>الوقت المنقضي:</b> <code>{elapsed_time}</code>\n\n"
                    f"{note_block}"
                    f"{files_block}\n\n"
                    f"<i>يعمل النظام بـ 5 عمال متوازيين، يرجى الانتظار حتى يتم تجميع كل الملفات.</i>"
                )
            else:
                text = (
                    f"{progress_bar}\n\n"
                    f"✅ <b>تمت معالجة الصور بنجاح وتخزينها في الجلسة.</b>\n\n"
                    f"📊 <b>إحصائيات الجلسة الحالية:</b>\n"
                    f"• إجمالي الصور المرسلة: <code>{total_received}</code>\n"
                    f"• تمت ترجمتها: <code>{processed_pages}</code>\n"
                    f"• قيد المعالجة الآن: <code>{processing_count}</code>\n"
                    f"• في الطابور: <code>{queue_size}</code>\n"
                    f"⏱ <b>الوقت المنقضي:</b> <code>{elapsed_time}</code>\n\n"
                    f"{note_block}"
                    f"{files_block}\n\n"
                    f"<i>يمكنك متابعة الإرسال، أو اضغط 🔴 إنهاء الجلسة لتجميع الملفات.</i>"
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
                    logger.error(f"Failed to create new tracker: {e}")
        finally:
            await self._batch.release_tracker_lock(job.user_id)

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
        
        note = await self._batch.get_session_note(user_id) or None

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
                            await asyncio.sleep(0.5)
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
                await self._batch.acquire_chat_send_lock(chat_id)
                try:
                    if fmt in ["txt", "both"]:
                        file_io = await asyncio.to_thread(handler.generate_txt, session_data, note)
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
                        file_io = await asyncio.to_thread(handler.generate_docx, session_data, note)
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
                    await self._batch.release_chat_send_lock(chat_id)
                    
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

            # Persistent Session Log
            tracker_id = await self._batch.get_tracker(user_id)
            total_images = len(session_data)
            start_time = await self._batch.get_session_start_time(user_id)
            elapsed_secs = int(_time.time() - start_time) if start_time else 0
            hours, rem = divmod(elapsed_secs, 3600)
            mins, secs = divmod(rem, 60)
            elapsed_time = f"{hours:02d}:{mins:02d}:{secs:02d}"
            
            log_text = (
                f"✅ <b>اكتملت الجلسة</b>\n"
                f"📄 <b>الاسم:</b> <code>{escape_html(base_filename)}</code>\n"
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