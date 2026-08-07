# File: systems/delivery/ui/handlers/messages.py
from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime, timezone
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import RetryAfter, BadRequest

from utils.markdown_escaper import escape_html

logger = logging.getLogger(__name__)

def _cancel_deferred_tracker_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    task = context.user_data.pop('deferred_tracker_task', None)
    if task and not task.done():
        task.cancel()

def _schedule_deferred_tracker_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _cancel_deferred_tracker_update(context)
    context.user_data['deferred_tracker_task'] = asyncio.create_task(
        _deferred_tracker_runner(update, context)
    )

async def _deferred_tracker_runner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await asyncio.sleep(0.6)
        await _render_intake_tracker(update, context)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Deferred tracker failed: {e}")

async def _render_intake_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    batch_manager = container.batch
    bot = context.bot
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    await batch_manager.acquire_tracker_lock(user_id)
    try:
        context.user_data['last_intake_update'] = _time.time()
        
        force_new = context.user_data.pop('force_new_tracker', False)
        tracker_id = await batch_manager.get_tracker(user_id)
        
        if force_new and tracker_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=tracker_id)
            except Exception:
                pass
            tracker_id = None
            await batch_manager.set_tracker(user_id, None)
            
        pending_files = await batch_manager.get_pending_files(user_id)
        pending_count = len(pending_files)
        
        file_names_html = [escape_html(f[1]) for f in pending_files if f[1]]
        if len(file_names_html) > 25:
            start_index = len(file_names_html) - 10
            files_text = "… عرض آخر 10 صور\n" + "\n".join(
                [f"{i}. {name}" for i, name in enumerate(file_names_html[-10:], start=start_index + 1)]
            )
        else:
            files_text = "\n".join([f"{i}. {name}" for i, name in enumerate(file_names_html, start=1)])
            
        files_block = f"<blockquote expandable>📥 <b>الصور المستلمة ({pending_count}):</b>\n{files_text}</blockquote>"
        
        note = await batch_manager.get_session_note(user_id)
        note_html = escape_html(note) if note else ""
        note_block = f"\n📝 <b>ملاحظة:</b>\n{note_html}\n" if note_html else ""
        
        start_time = await batch_manager.get_session_start_time(user_id)
        elapsed_secs = int(_time.time() - start_time) if start_time else 0
        hours, rem = divmod(elapsed_secs, 3600)
        mins, secs = divmod(rem, 60)
        elapsed_time = f"{hours:02d}:{mins:02d}:{secs:02d}"
        
        text = (
            f"📥 <b>جاري استلام الصور وتجهيزها للجلسة...</b>\n\n"
            f"⏱ <b>الوقت المنقضي:</b> <code>{elapsed_time}</code>\n\n"
            f"{files_block}\n"
            f"{note_block}\n\n"
            f"<i>عند الانتهاء من إرسال كل الصور، اضغط زر 🔴 إنهاء الجلسة لبدء الترجمة.</i>"
        )
        
        if tracker_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=tracker_id,
                    text=text, parse_mode=ParseMode.HTML
                )
                return
            except BadRequest as e:
                err_str = str(e).lower()
                if "message is not modified" in err_str:
                    return
                if "message to edit not found" in err_str or "message can't be edited" in err_str:
                    await batch_manager.set_tracker(user_id, None)
                    tracker_id = None
                else:
                    return
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=tracker_id,
                        text=text, parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass
                return
            except Exception:
                return
            
        if not tracker_id:
            try:
                msg = await bot.send_message(
                    chat_id=chat_id, text=text, parse_mode=ParseMode.HTML
                )
                await batch_manager.set_tracker(user_id, msg.message_id)
            except Exception as e:
                logger.error(f"Failed to create intake tracker: {e}")
    finally:
        await batch_manager.release_tracker_lock(user_id)

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    batch_manager = container.batch
    
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
            text="↩️ *تم إلغاء انتظار الاسم وإضافة الصورة للاستلام\\.*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    # Phase 1: Intake & Caching Engine (Zero Network Usage for AI)
    await batch_manager.add_pending_file(user.id, image_file_id, file_name, update.message.message_id)
    await batch_manager.add_session_photo_id(user.id, update.message.message_id)
    
    # 3-Second Floating Rule Evaluation
    current_msg_time = update.message.date if update.message.date else datetime.now(timezone.utc)
    last_msg_time = context.user_data.get('last_image_time')
    
    is_new_batch = not last_msg_time or (current_msg_time - last_msg_time).total_seconds() > 3.0
    context.user_data['last_image_time'] = current_msg_time
    
    if is_new_batch:
        context.user_data['force_new_tracker'] = True
        
    # Smart Flood Shield
    current_time = _time.time()
    last_update_time = context.user_data.get('last_intake_update', 0.0)
    
    if current_time - last_update_time < 0.5:
        # Schedule deferred task to catch up with the rest of the burst
        _schedule_deferred_tracker_update(update, context)
        return
        
    # Passed shield, render immediately and cancel any pending deferred task
    _cancel_deferred_tracker_update(context)
    await _render_intake_tracker(update, context)

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