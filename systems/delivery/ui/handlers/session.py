# File: systems/delivery/ui/handlers/session.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from utils.markdown_escaper import escape_markdown_v2, sanitize_filename

logger = logging.getLogger(__name__)

async def _perform_cancel(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE, message_to_delete: Optional[int] = None) -> None:
    container = context.bot_data["container"]
    context.user_data['awaiting_session_filename'] = False
    await container.batch.set_finalizing(user_id, False)
    
    tracker_id = await container.batch.get_tracker(user_id)
    if tracker_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=tracker_id)
        except Exception:
            pass
        
    prompt_msg_id = await container.batch.get_prompt_message_id(user_id)
    if prompt_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prompt_msg_id)
        except Exception:
            pass
        
    await container.batch.clear_session(user_id)
        
    try:
        await context.bot.send_message(chat_id=chat_id, text="🚪 *تم إلغاء العملية وحذف بيانات الجلسة بنجاح\\.*", parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        pass
    
    if message_to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_to_delete)
        except Exception:
            pass

async def _initiate_flush(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    pending_files = await container.batch.get_pending_files(user_id)
    text = (
        "⏳ <b>جاري ترجمة الصور وتجميع الملف...</b>\n\n"
        "📊 <b>إحصائيات الجلسة الحالية:</b>\n"
        f"• إجمالي الصور: <code>{len(pending_files)}</code>\n"
        "• تمت ترجمتها: <code>0</code>\n"
        "• قيد المعالجة الآن: <code>0</code>\n"
        "• في الطابور: <code>0</code>\n\n"
        "<i>يعمل النظام بـ 5 عمال متوازيين، يرجى الانتظار حتى يتم تجميع كل الملفات.</i>"
    )
    
    try:
        msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        await container.batch.set_tracker(user_id, msg.message_id)
        await container.batch.force_update_tracker(user_id)
    except Exception as e:
        logger.error(f"Failed to create grouped processing tracker: {e}")
        
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await container.delivery.flush_pending_to_queue(user_id, chat_id)

async def start_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    
    context.user_data['awaiting_session_filename'] = False
    await container.batch.set_finalizing(user_id, False)
    
    persona_name = await container.settings.get_persona(user_id)
    if not persona_name:
        persona_name = "Default Translator"
        
    session_mode = await container.settings.get_session_mode(user_id)
    if not session_mode:
        session_mode = "grouped"
        
    await container.batch.start_session(user_id, persona_name, session_mode)
    
    mode_text = "تجميع جماعي (ملف واحد لكل الجلسة)" if session_mode == "grouped" else "تجميع فردي (ملف لكل صورة)"
    
    text = (
        f"🎬 *تم تفعيل وضع الجلسة بنجاح\\!*\n\n"
        f"📦 *وضع الجلسة الحالي:* {escape_markdown_v2(mode_text)}\n\n"
        "في هذا الوضع، تم تفعيل *الحماية القصوى* لمنع التشتت:\n"
        "• سيتم قبول *صور المانغا فقط*\\.\n"
        "• يمكنك إرسال *أي عدد من الصور* دفعة واحدة أو تباعاً\\.\n"
        "• سيتم *حذف* أي رسالة نصية، ملصق، أو أمر فوراً\\.\n\n"
    )
    
    if session_mode == "grouped":
        text += "⚠️ *للخروج من هذا الوضع وتجميع الملفات:* اضغط زر *🔴 إنهاء الجلسة*\\.\n"
    else:
        text += "⚠️ *في هذا الوضع سيتم إرسال ملف الترجمة فور انتهاء معالجة كل صورة*\\.\n"
        
    text += "🚪 _لإلغاء الجلسة بالكامل في أي وقت، أرسل: /cancel_\n"
    text += "📝 _لإضافة ملاحظة تظهر في الملف، أرسل: /note ملاحظتك_"
    
    await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2)

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    
    if not await container.batch.is_session_active(user_id):
        return
        
    note_text = update.message.text.replace('/note', '').strip()
    if not note_text:
        try:
            await update.message.delete()
        except Exception:
            pass
        return
        
    await container.batch.set_session_note(user_id, note_text)
    
    try:
        await update.message.delete()
    except Exception:
        pass
        
    # Force tracker update to show the note immediately
    context.user_data['force_new_tracker'] = True
    from systems.delivery.ui.handlers.messages import _render_intake_tracker
    await _render_intake_tracker(update, context)

async def end_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await container.batch.is_session_active(user_id):
        await update.message.reply_text("⚠️ *لا توجد جلسة نشطة حالياً\\.*\nاضغط *🟢 بدء الجلسة* أولاً قبل إرسال الصور\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    pending_files = await container.batch.get_pending_files(user_id)
    if not pending_files:
        await update.message.reply_text("⚠️ *الجلسة فارغة\\.*\nلم تقم بإرسال أي صور صالحة\\. أرسل صوراً أولاً ثم أنهِ الجلسة\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    # Delete intake tracker
    tracker_id = await container.batch.get_tracker(user_id)
    if tracker_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=tracker_id)
        except Exception:
            pass
        await container.batch.set_tracker(user_id, None)

    session_mode = await container.batch.get_session_mode(user_id)
    
    # Mark as finalizing and pending compile for both modes
    await container.batch.set_finalizing(user_id, True)
    await container.batch.set_pending_compile(user_id)
    
    if session_mode == "individual":
        text = (
            "⏳ <b>جاري ترجمة الصور وإرسالها فردياً...</b>\n\n"
            "📊 <b>إحصائيات الجلسة الحالية:</b>\n"
            f"• إجمالي الصور: <code>{len(pending_files)}</code>\n"
            "• تمت ترجمتها: <code>0</code>\n"
            "• قيد المعالجة الآن: <code>0</code>\n"
            "• في الطابور: <code>0</code>\n\n"
            "<i>يعمل النظام بـ 5 عمال متوازيين، يرجى الانتظار حتى يتم إرسال كل الملفات.</i>"
        )
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
            await container.batch.set_tracker(user_id, msg.message_id)
            await container.batch.force_update_tracker(user_id)
        except Exception as e:
            logger.error(f"Failed to create individual processing tracker: {e}")
            
        await container.delivery.flush_pending_to_queue(user_id, chat_id)
        return

    # Grouped mode
    context.user_data['awaiting_session_filename'] = True
    
    text = (
        "📝 *تسمية ملف الترجمة*\n\n"
        "يرجى إرسال الاسم الذي تريد حفظ ملف الترجمة به الآن\\.\n\n"
        "⚠️ _ملاحظة: تم إيقاف استقبال الصور حتى نهاية التجميع\\._\n\n"
        "🚪 _لإلغاء العملية والخروج، أرسل الأمر: /cancel_"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ تخطي (اسم تلقائي)", callback_data="skip_filename")],
        [InlineKeyboardButton("⏹️ إلغاء الجلسة", callback_data="cancel_session_btn")]
    ])
    
    try:
        prompt_msg = await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
        await container.batch.set_prompt_message_id(user_id, prompt_msg.message_id)
    except Exception as e:
        logger.error(f"Failed to send filename prompt: {e}")
        context.user_data['awaiting_session_filename'] = False
        await container.batch.set_finalizing(user_id, False)
        await update.message.reply_text("⚠️ حدث خطأ فني، يرجى المحاولة مرة أخرى\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def skip_filename_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    if not await container.batch.is_session_active(user_id):
        return
        
    default_name = f"Manga_Session_{datetime.now().strftime('%Y-%m-%d_%H-%M')}"
    await container.batch.set_custom_filename(user_id, default_name)
    
    prompt_msg_id = await container.batch.get_prompt_message_id(user_id)
    if prompt_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prompt_msg_id)
            await container.batch.set_prompt_message_id(user_id, None)
        except Exception:
            pass
            
    context.user_data['awaiting_session_filename'] = False
    await _initiate_flush(user_id, chat_id, context)

async def cancel_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    if not await container.batch.is_session_active(user_id):
        return
        
    await _perform_cancel(user_id, chat_id, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    is_active = await container.batch.is_session_active(user_id)
    is_finalizing = await container.batch.is_finalizing(user_id)
    
    if not is_active and not is_finalizing and not context.user_data.get('awaiting_session_filename'):
        try:
            await update.message.delete()
        except Exception:
            pass
        return
            
    await _perform_cancel(user_id, chat_id, context, update.message.message_id)

async def receive_session_filename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    context.user_data['awaiting_session_filename'] = False
    
    raw_filename = update.message.text
    clean_filename = sanitize_filename(raw_filename)
    
    await container.batch.set_custom_filename(user_id, clean_filename)
    
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass
    
    prompt_msg_id = await container.batch.get_prompt_message_id(user_id)
    if prompt_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prompt_msg_id)
            await container.batch.set_prompt_message_id(user_id, None)
        except Exception:
            pass

    await _initiate_flush(user_id, chat_id, context)

async def handle_cleanup_photos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    container = context.bot_data["container"]
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    await query.answer("جاري تنظيف الشات...", show_alert=False)
    
    photo_ids = await container.batch.get_session_photo_ids(user_id)
    
    deleted_count = 0
    for msg_id in photo_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            deleted_count += 1
            await asyncio.sleep(0.05)  # slight delay to avoid flood
        except Exception:
            pass
            
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=query.message.message_id, reply_markup=None
        )
        await query.answer(f"تم حذف {deleted_count} صورة.", show_alert=True)
    except Exception:
        pass