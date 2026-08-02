# systems/delivery/ui/handlers/session.py
from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from utils.markdown_escaper import escape_markdown_v2, sanitize_filename

logger = logging.getLogger(__name__)

async def start_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    
    context.user_data['awaiting_session_filename'] = False
    await container.batch.set_finalizing(user_id, False)
    
    persona_name = await container.settings.get_persona(user_id)
    if not persona_name:
        persona_name = "Default Translator"
    await container.batch.start_session(user_id, persona_name)
    
    text = (
        "🎬 *تم تفعيل وضع الجلسة بنجاح\\!*\n\n"
        "في هذا الوضع، تم تفعيل *الحماية القصوى* لمنع التشتت:\n"
        "• سيتم قبول *صور المانغا فقط*\\.\n"
        "• يمكنك إرسال *أي عدد من الصور* دفعة واحدة أو تباعاً\\.\n"
        "• سيتم *حذف* أي رسالة نصية، ملصق، أو أمر فوراً\\.\n\n"
        "⚠️ *للخروج من هذا الوضع وتجميع الملفات:* اضغط زر *🔴 إنهاء الجلسة*\\.\n"
        "🚪 _لإلغاء الجلسة بالكامل في أي وقت، أرسل: /cancel_"
    )
    await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2)

async def end_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    
    if not await container.batch.is_session_active(user_id):
        await update.message.reply_text("⚠️ *لا توجد جلسة نشطة حالياً\\.*\nاضغط *🟢 بدء الجلسة* أولاً قبل إرسال الصور\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    session_data = await container.batch.get_session_data(user_id)
    if not session_data:
        await update.message.reply_text("⚠️ *الجلسة فارغة\\.*\nلم تقم بإرسال أي صور صالحة\\. أرسل صوراً أولاً ثم أنهِ الجلسة\\.", parse_mode=ParseMode.MARKDOWN_V2)
        await container.batch.clear_session(user_id)
        return

    await container.batch.set_finalizing(user_id, True)
    context.user_data['awaiting_session_filename'] = True
    
    text = (
        "📝 *تسمية ملف الترجمة*\n\n"
        "يرجى إرسال الاسم الذي تريد حفظ ملف الترجمة به الآن\\.\n\n"
        "⚠️ _ملاحظة: تم إيقاف استقبال الصور حتى نهاية التجميع\\._\n\n"
        "🚪 _لإلغاء العملية والخروج، أرسل الأمر: /cancel_"
    )
    
    try:
        prompt_msg = await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2)
        await container.batch.set_prompt_message_id(user_id, prompt_msg.message_id)
    except Exception as e:
        logger.error(f"Failed to send filename prompt: {e}")
        context.user_data['awaiting_session_filename'] = False
        await container.batch.set_finalizing(user_id, False)
        await update.message.reply_text("⚠️ حدث خطأ فني، يرجى المحاولة مرة أخرى\\.", parse_mode=ParseMode.MARKDOWN_V2)

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
    
    try:
        await update.message.delete()
    except Exception:
        pass

async def receive_session_filename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    
    context.user_data['awaiting_session_filename'] = False
    
    raw_filename = update.message.text
    clean_filename = sanitize_filename(raw_filename)
    escaped_filename = escape_markdown_v2(clean_filename)
    
    await container.batch.set_custom_filename(user_id, clean_filename)
    
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except Exception:
        pass
    
    queue_size = await container.queue.size()
    
    if queue_size > 0:
        await container.batch.set_pending_compile(user_id)
        msg_text = f"⏳ *تم تسجيل اسم الملف:* `{escaped_filename}`\nلا تزال لديك صور قيد المعالجة\\. سيقوم البوت بتجميع الملف وإرساله فور اكتمالها\\."
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_text, parse_mode=ParseMode.MARKDOWN_V2)
        return

    msg_text = f"⏳ *جاري تجميع الترجمة بإسم:* `{escaped_filename}`\\.\\.\\."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_text, parse_mode=ParseMode.MARKDOWN_V2)
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)
    
    await container.delivery.compile_session(user_id, update.effective_chat.id)