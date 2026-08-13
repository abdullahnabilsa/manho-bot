# File: systems/delivery/ui/handlers/session.py
from __future__ import annotations

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction
from telegram.error import RetryAfter, BadRequest

from utils.markdown_escaper import escape_markdown_v2, sanitize_filename
from systems.delivery.pipeline import FlushResult

logger = logging.getLogger(__name__)

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
    
    await container.batch.add_transient_message(user_id, update.message.message_id)
    
    mode_text = "تجميع موحد (ملف واحد لكل الجلسة)" if session_mode == "grouped" else "تجميع فردي (ملف لكل صورة)"
    
    text = (
        "🎬 *تم بدء الجلسة بنجاح\\.*\n\n"
        f"📦 *وضع التجميع:* {escape_markdown_v2(mode_text)}\n\n"
        "تم تفعيل *وضع الحماية* لضمان تجربة خالية من التشتت:\n"
        "• يقبل البوت *صور المانغا فقط*\\.\n"
        "• يمكنك إرسال الصور دفعة واحدة أو تباعاً\\.\n"
        "• سيتم *تجاهل وحذف* أي رسائل نصية أو أوامر غير مصرح بها فوراً\\.\n\n"
        "⚠️ عند الانتهاء، اضغط *🔴 إنهاء الجلسة* لبدء الترجمة والتجميع\\.\n"
        "🚪 للإلغاء الكامل والخروج، أرسل: `/cancel`"
    )
    
    reply_msg = await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2)
    await container.batch.add_transient_message(user_id, reply_msg.message_id)

async def set_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    
    if not await container.batch.is_session_active(user_id):
        try:
            await update.message.delete()
        except Exception:
            pass
        return
        
    note_text = update.message.text[len("/note"):].strip()
    if not note_text:
        await update.message.reply_text(
            "⚠️ يرجى كتابة الملاحظة بعد الأمر\\. مثال: `/note هذا الفصل يركز على الحركة`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    await container.batch.set_session_note(user_id, note_text)
    
    try:
        await update.message.delete()
    except Exception:
        pass
        
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📝 *تم حفظ الملاحظة\\.*\nسيتم إظهارها في رسالة الإحصائيات وإضافتها لملف الترجمة\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def end_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    await container.batch.add_transient_message(user_id, update.message.message_id)
    
    if not await container.batch.is_session_active(user_id):
        await update.message.reply_text("⚠️ *لا توجد جلسة نشطة حالياً\\.*\nاضغط *🟢 بدء الجلسة* أولاً قبل إرسال الصور\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    pending_files = await container.batch.get_pending_files(user_id)
    if not pending_files:
        context.user_data['awaiting_session_filename'] = False
        await container.batch.clear_session(user_id)
        
        try:
            await update.message.delete()
        except Exception:
            pass
            
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ *لا توجد صور للمعالجة\\.*\nتم إغلاق الجلسة الفارغة\\.\nيمكنك الآن استخدام الأوامر العادية\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    tracker_id = await container.batch.get_tracker(user_id)
    if tracker_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=tracker_id)
        except Exception:
            pass
        await container.batch.set_tracker(user_id, None)

    session_mode = await container.batch.get_session_mode(user_id)
    
    await container.batch.set_finalizing(user_id, True)
    await container.batch.set_pending_compile(user_id)
    
    if session_mode == "individual":
        result = await container.delivery.flush_pending_to_queue(user_id, chat_id)
        if result == FlushResult.WAITING:
            text = (
                "⏳ *النظام يعمل بطاقته القصوى حالياً\\.*\n"
                "تمت إضافتك لقائمة الانتظار\\.\n\n"
                "_سيتم بدء معالجة صورك وإرسال الملفات تلقائياً فور انتهاء الجلسة الحالية\\._"
            )
            try:
                msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
                await container.batch.set_waiting_message_id(user_id, msg.message_id)
            except Exception:
                pass
            return
        elif result == FlushResult.QUEUE_FULL:
            await context.bot.send_message(chat_id=chat_id, text="🚨 الضغط على النظام مرتفع جداً. يرجى المحاولة لاحقاً.")
            await container.batch.clear_session(user_id)
            return
        elif result == FlushResult.ALLOWED:
            text = (
                "⚙️ *بدأت المعالجة الفردية...*\n\n"
                "📊 *إحصائيات الجلسة:*\n"
                f"• إجمالي الصور: `{len(pending_files)}`\n"
                "• تمت ترجمتها: `0`\n"
                "• قيد المعالجة: `0`\n"
                "• في الطابور: `0`\n\n"
                "_يعمل النظام بعدد ثابت من العمال المتوازيين، سيتم إرسال ملف لكل صورة فور انتهائها\\._"
            )
            try:
                msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
                await container.batch.set_tracker(user_id, msg.message_id)
                await container.batch.force_update_tracker(user_id)
            except Exception as e:
                logger.error(f"Failed to create individual processing tracker: {e}")
            return

    context.user_data['awaiting_session_filename'] = True
    
    text = (
        "📝 *تسمية ملف الترجمة*\n\n"
        "يرجى إرسال الاسم الذي تريد حفظ ملف الترجمة به الآن\\.\n\n"
        "⚠️ _ملاحظة: تم إيقاف استقبال الصور حتى نهاية التجميع\\._\n\n"
        "🚪 _لإلغاء العملية والخروج، أرسل الأمر: /cancel_"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏩ تخطي (اسم تلقائي)", callback_data="skip_filename"),
            InlineKeyboardButton("⏹️ إلغاء الجلسة", callback_data="cancel_session")
        ]
    ])
    
    try:
        prompt_msg = await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
        await container.batch.set_prompt_message_id(user_id, prompt_msg.message_id)
    except Exception as e:
        logger.error(f"Failed to send filename prompt: {e}")
        context.user_data['awaiting_session_filename'] = False
        await container.batch.set_finalizing(user_id, False)
        await update.message.reply_text("⚠️ حدث خطأ فني، يرجى المحاولة مرة أخرى\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def handle_skip_filename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    if not await container.batch.is_session_active(user_id):
        await query.edit_message_text("⚠️ الجلسة غير نشطة.")
        return
        
    default_name = f"Manga_Session_{datetime.now().strftime('%d-%m-%Y')}"
    await container.batch.set_custom_filename(user_id, default_name)
    
    try:
        await query.message.delete()
    except Exception:
        pass
        
    context.user_data['awaiting_session_filename'] = False
    
    prompt_msg_id = await container.batch.get_prompt_message_id(user_id)
    if prompt_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prompt_msg_id)
            await container.batch.set_prompt_message_id(user_id, None)
        except Exception:
            pass

    pending_files = await container.batch.get_pending_files(user_id)
    result = await container.delivery.flush_pending_to_queue(user_id, chat_id)
    
    if result == FlushResult.WAITING:
        text = (
            "⏳ *النظام يعمل بطاقته القصوى حالياً\\.*\n"
            "تمت إضافتك لقائمة الانتظار\\.\n\n"
            "_سيتم بدء معالجة صورك وإرسال الملفات تلقائياً فور انتهاء الجلسة الحالية\\._"
        )
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
            await container.batch.set_waiting_message_id(user_id, msg.message_id)
        except Exception:
            pass
        return
    elif result == FlushResult.QUEUE_FULL:
        await context.bot.send_message(chat_id=chat_id, text="🚨 الضغط على النظام مرتفع جداً. يرجى المحاولة لاحقاً.")
        await container.batch.clear_session(user_id)
        return
    elif result == FlushResult.ALLOWED:
        text = (
            "⚙️ *بدأت المعالجة والتجميع...*\n\n"
            "📊 *إحصائيات الجلسة:*\n"
            f"• إجمالي الصور: `{len(pending_files)}`\n"
            "• تمت ترجمتها: `0`\n"
            "• قيد المعالجة: `0`\n"
            "• في الطابور: `0`\n\n"
            "_يعمل النظام بعدد ثابت من العمال المتوازيين، يرجى الانتظار حتى يتم تجميع كل الملفات\\._"
        )
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
            await container.batch.set_tracker(user_id, msg.message_id)
            await container.batch.force_update_tracker(user_id)
        except Exception as e:
            logger.error(f"Failed to create grouped processing tracker: {e}")
            
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

async def handle_cancel_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
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
        await query.message.delete()
    except Exception:
        pass
        
    try:
        await context.bot.send_message(chat_id=chat_id, text="🚪 *تم إلغاء الجلسة وتنظيف البيانات بنجاح\\.*", parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        pass

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    is_active = await container.batch.is_session_active(user_id)
    is_finalizing = await container.batch.is_finalizing(user_id)
    is_queue_active = await container.jobs.is_active_user(user_id)
    
    if not is_active and not is_finalizing and not context.user_data.get('awaiting_session_filename'):
        await container.jobs.cancel_waiting_user(user_id)
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
    
    if is_queue_active:
        next_user = await container.jobs.release_active_user()
        if next_user:
            next_user_id, next_chat_id = next_user
            await container.delivery.activate_waiting_user(next_user_id, next_chat_id)
    else:
        await container.jobs.cancel_waiting_user(user_id)
        
    try:
        await context.bot.send_message(chat_id=chat_id, text="🚪 *تم إلغاء الجلسة وتنظيف البيانات بنجاح\\.*", parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        pass
    
    try:
        await update.message.delete()
    except Exception:
        pass

async def receive_session_filename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    context.user_data['awaiting_session_filename'] = False
    
    raw_filename = update.message.text
    clean_filename = sanitize_filename(raw_filename)
    escaped_filename = escape_markdown_v2(clean_filename)
    
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

    pending_files = await container.batch.get_pending_files(user_id)
    result = await container.delivery.flush_pending_to_queue(user_id, chat_id)
    
    if result == FlushResult.WAITING:
        text = (
            "⏳ *النظام يعمل بطاقته القصوى حالياً\\.*\n"
            "تمت إضافتك لقائمة الانتظار\\.\n\n"
            "_سيتم بدء معالجة صورك وإرسال الملفات تلقائياً فور انتهاء الجلسة الحالية\\._"
        )
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
            await container.batch.set_waiting_message_id(user_id, msg.message_id)
        except Exception:
            pass
        return
    elif result == FlushResult.QUEUE_FULL:
        await context.bot.send_message(chat_id=chat_id, text="🚨 الضغط على النظام مرتفع جداً. يرجى المحاولة لاحقاً.")
        await container.batch.clear_session(user_id)
        return
    elif result == FlushResult.ALLOWED:
        text = (
            f"✅ *تم حفظ الاسم:* `{escaped_filename}`\n\n"
            "⚙️ *بدأت المعالجة والتجميع...*\n\n"
            "📊 *إحصائيات الجلسة:*\n"
            f"• إجمالي الصور: `{len(pending_files)}`\n"
            "• تمت ترجمتها: `0`\n"
            "• قيد المعالجة: `0`\n"
            "• في الطابور: `0`\n\n"
            "_يعمل النظام بعدد ثابت من العمال المتوازيين، يرجى الانتظار حتى يتم تجميع كل الملفات\\._"
        )
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
            await container.batch.set_tracker(user_id, msg.message_id)
            await container.batch.force_update_tracker(user_id)
        except Exception as e:
            logger.error(f"Failed to create grouped processing tracker: {e}")
            
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

async def handle_cleanup_photos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Phase 3: Cleanup Engine - Deletes original photos and transient messages in bulk."""
    query = update.callback_query
    await query.answer("جاري تنظيف الشات...", show_alert=False)
    container = context.bot_data["container"]
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    cleanup_ids = await container.batch.get_cleanup_photo_ids(user_id)
    if not cleanup_ids:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
        
    for i in range(0, len(cleanup_ids), 100):
        chunk = cleanup_ids[i:i+100]
        try:
            await context.bot.delete_messages(chat_id=chat_id, message_ids=chunk)
        except BadRequest as e:
            if "message to delete not found" in str(e).lower():
                continue
            logger.warning(f"BadRequest during cleanup: {e}")
        except Exception as e:
            logger.warning(f"Failed to delete some messages: {e}")
            
    await container.batch.clear_cleanup_photo_ids(user_id)
            
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass