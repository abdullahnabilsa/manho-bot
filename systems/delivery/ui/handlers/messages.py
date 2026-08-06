# systems/delivery/ui/handlers/messages.py
from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime, timezone
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction
from telegram.error import RetryAfter, TelegramError

from systems.translation_pipeline.models.page_job import PageJob
from utils.markdown_escaper import escape_markdown_v2, escape_html
from systems.job_orchestration.worker import JobSubmissionResult

logger = logging.getLogger(__name__)

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    job_manager = container.jobs
    queue_manager = container.queue
    batch_manager = container.batch
    settings_manager = container.settings
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if await batch_manager.is_finalizing(user.id):
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    is_session_active = await batch_manager.is_session_active(user.id)
    if not is_session_active:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ *يرجى بدء جلسة أولاً*\n\nاضغط زر *🟢 بدء الجلسة* قبل إرسال الصور لترجمتها\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception:
            pass
        return

    image_file_id: Optional[str] = None
    file_name: Optional[str] = None
    
    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        file_name = f"Photo_{update.message.message_id}.jpg"
    elif update.message.document:
        mime_type = update.message.document.mime_type
        if mime_type and mime_type.startswith('image/'):
            image_file_id = update.message.document.file_id
            file_name = update.message.document.file_name or f"Document_{update.message.message_id}.jpg"
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🚫 *ملف غير مدعوم\\.*\nيرجى إرسال صورة بصيغة JPG أو PNG\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

    if not image_file_id:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ *خطأ في الاستلام\\.*\nلم أتمكن من قراءة الصورة، يرجى إعادة إرسالها\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    if context.user_data.get('awaiting_session_filename'):
        context.user_data['awaiting_session_filename'] = False
        await context.bot.send_message(
            chat_id=chat_id,
            text="↩️ *تم إلغاء انتظار الاسم وإضافة الصورة للطابور\\.*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    await batch_manager.increment_received_count(user.id)
    
    queue_size_before = await queue_manager.size()
    
    job = PageJob(
        user_id=user.id, 
        chat_id=chat_id, 
        image_file_id=image_file_id, 
        file_name=file_name,
        photo_message_id=update.message.message_id
    )
    
    submission_result = await job_manager.submit_job(job)
    
    if submission_result == JobSubmissionResult.QUEUE_FULL:
        await context.bot.send_message(
            chat_id=chat_id, 
            text="🚨 *النظام مشغول جداً حالياً\\.*\nلقد وصل الطابور العام إلى الحد الأقصى\\. يرجى الانتظار دقيقة وإعادة إرسال الصور\\.", 
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    session_mode = await batch_manager.get_session_mode(user.id)
    
    if session_mode == "grouped":
        tracker_id = await batch_manager.get_tracker(user.id)
        
        current_msg_time = update.message.date if update.message.date else datetime.now(timezone.utc)
        last_msg_time = context.user_data.get('last_image_time')
        
        is_new_batch = not last_msg_time or (current_msg_time - last_msg_time).total_seconds() > 3.0
        context.user_data['last_image_time'] = current_msg_time
        
        if is_new_batch and tracker_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=tracker_id)
            except Exception:
                pass
            await batch_manager.set_tracker(user.id, None)
            tracker_id = None
        
        if not tracker_id:
            current_queue = await queue_manager.size()
            translated_count = len(await batch_manager.get_session_data(user.id))
            total_received = await batch_manager.get_received_count(user.id)
            processing_count = total_received - translated_count - current_queue
            if processing_count < 0:
                processing_count = 0
                
            start_time = await batch_manager.get_session_start_time(user.id)
            elapsed_secs = int(_time.time() - start_time) if start_time else 0
            hours, rem = divmod(elapsed_secs, 3600)
            mins, secs = divmod(rem, 60)
            elapsed_time = f"{hours:02d}:{mins:02d}:{secs:02d}"
                
            text = (
                f"⏳ <b>تم استلام الصور وجاري بدء المعالجة...</b>\n\n"
                f"📊 <b>إحصائيات الجلسة الحالية:</b>\n"
                f"• إجمالي الصور المرسلة: <code>{total_received}</code>\n"
                f"• تمت ترجمتها: <code>{translated_count}</code>\n"
                f"• قيد المعالجة الآن: <code>{processing_count}</code>\n"
                f"• في الطابور: <code>{current_queue}</code>\n"
                f"⏱ <b>الوقت المنقضي:</b> <code>{elapsed_time}</code>\n\n"
                f"<i>يرجى الانتظار، الذكاء الاصطناعي يحلل الصور...</i>"
            )
            try:
                msg = await context.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode=ParseMode.HTML
                )
                await batch_manager.set_tracker(user.id, msg.message_id)
            except Exception:
                pass
        else:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
    else:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('awaiting_glossary_upload'):
        context.user_data['awaiting_glossary_upload'] = False
        container = context.bot_data["container"]
        
        if not update.message.document:
            await update.message.reply_text("⚠️ يرجى إرسال ملف بصيغة txt\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return
            
        try:
            tg_file = await update.message.document.get_file()
            file_bytes = await tg_file.download_as_bytearray()
            
            success = await container.glossary.save_glossary(bytes(file_bytes))
            if success:
                await update.message.reply_text(
                    "✅ *تم تحديث القاموس بنجاح\\!*\nسيتم استخدامه في الترجمات القادمة\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await update.message.reply_text(
                    "❌ *فشل التحديث*\nالملف غير صالح أو لا يحتوي على JSON سليم\\. يرجى التحقق من التنسيق\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
        except Exception as e:
            logger.error(f"Error uploading glossary: {e}")
            await update.message.reply_text(
                "❌ حدث خطأ فني أثناء رفع الملف\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    else:
        await update.message.reply_text(
            "ℹ️ لا يمكنني معالجة هذا الملف حالياً\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('awaiting_user_api_key'):
        from systems.delivery.ui.handlers.api_keys import receive_user_api_key
        await receive_user_api_key(update, context)
    elif context.user_data.get('awaiting_admin_api_key'):
        from systems.delivery.ui.handlers.admin import receive_admin_api_key
        await receive_admin_api_key(update, context)
    elif context.user_data.get('awaiting_add_user'):
        from systems.delivery.ui.handlers.access import receive_add_user
        await receive_add_user(update, context)
    elif context.user_data.get('awaiting_session_filename'):
        from systems.delivery.ui.handlers.session import receive_session_filename
        await receive_session_filename(update, context)
    else:
        await update.message.reply_text(
            "ℹ️ *مرحباً\\!*\nيرجى إرسال صورة لترجمتها\\.\nاستخدم الأزرار بالأسفل للتحكم في البوت\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )