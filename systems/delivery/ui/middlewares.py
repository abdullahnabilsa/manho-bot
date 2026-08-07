# systems/delivery/ui/middlewares.py
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from shared.container import ServiceContainer
from systems.delivery.ui.handlers.session import receive_session_filename

async def state_purge_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('awaiting_session_filename'):
        if update.callback_query:
            await update.callback_query.answer("📝 يرجى إرسال اسم الملف فقط كنص أو /cancel للإلغاء.", show_alert=True)
            raise ApplicationHandlerStop
            
        msg = update.message
        if msg and msg.text in ["/cancel", "/start"]:
            return
            
        persistent_buttons = ["⚙️ الإعدادات", "📖 المساعدة", "🟢 بدء الجلسة", "🔴 إنهاء الجلسة"]
        is_plain_text = (
            msg and msg.text and not msg.text.startswith('/')
            and msg.text not in persistent_buttons
            and not msg.photo and not msg.document
        )
        
        if is_plain_text:
            await receive_session_filename(update, context)
            raise ApplicationHandlerStop
            
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass
            raise ApplicationHandlerStop

    is_command = update.message and update.message.text and update.message.text.startswith('/')
    is_callback = update.callback_query is not None
    is_media = update.message and (
        update.message.photo or
        (update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith('image/'))
    )
    is_persistent_btn = update.message and update.message.text in ["⚙️ الإعدادات", "📖 المساعدة", "🟢 بدء الجلسة", "🔴 إنهاء الجلسة"]
    
    is_system_interaction = is_command or is_callback or is_persistent_btn or is_media
    if (context.user_data.get('awaiting_admin_api_key') or context.user_data.get('awaiting_user_api_key') or context.user_data.get('awaiting_add_user')) and is_system_interaction:
        context.user_data['awaiting_admin_api_key'] = False
        context.user_data['awaiting_user_api_key'] = False
        context.user_data['awaiting_add_user'] = False

async def session_guard_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    container: ServiceContainer = context.bot_data["container"]
    user_id = update.effective_user.id
    
    if not await container.batch.is_session_active(user_id):
        return

    if context.user_data.get('awaiting_session_filename'):
        return
    if update.callback_query and update.callback_query.data.startswith(("accept_req", "reject_req")):
        return

    if update.callback_query:
        await update.callback_query.answer("🚫 معطل أثناء الجلسة. اضغط 🔴 إنهاء الجلسة للخروج.", show_alert=True)
        raise ApplicationHandlerStop

    if update.message and (update.message.photo or (update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith('image/'))):
        return

    if update.message and update.message.text:
        msg_text = update.message.text
        if msg_text in ["/end_session", "🔴 إنهاء الجلسة", "/cancel", "/start"] or msg_text.startswith("/note"):
            return

    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
    raise ApplicationHandlerStop