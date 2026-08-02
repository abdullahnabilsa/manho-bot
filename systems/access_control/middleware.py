# systems/access_control/middleware.py
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop
from telegram.constants import ParseMode

from utils.markdown_escaper import escape_markdown_v2
from shared.container import ServiceContainer

logger = logging.getLogger(__name__)

async def firewall_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user: return
    
    container: ServiceContainer = context.bot_data["container"]
    access_manager = container.access
    user_id = update.effective_user.id
    
    if await access_manager.is_authorized(user_id): return

    if await access_manager.is_join_requests_open():
        if update.message and update.message.text and update.message.text.startswith("/start"):
            if await access_manager.is_on_cooldown(user_id):
                try:
                    await context.bot.send_message(chat_id=user_id, text="⏳ لقد أرسلت طلباً للتو\\.\nيرجى الانتظار دقيقة قبل المحاولة مرة أخرى\\.", parse_mode=ParseMode.MARKDOWN_V2)
                except Exception: pass
                raise ApplicationHandlerStop

            old_requests = await access_manager.get_pending_requests(user_id)
            if old_requests:
                for adm_id, msg_id in old_requests:
                    try:
                        await context.bot.delete_message(chat_id=adm_id, message_id=msg_id)
                    except Exception:
                        pass
                await access_manager.clear_requests(user_id)

            user = update.effective_user
            try:
                await context.bot.send_message(chat_id=user_id, text="⏳ *تم استلام طلبك للانضمام إلى البوت\\.*\nسيقوم المشرفون بمراجعة طلبك\\. ستصلك رسالة فور الموافقة\\.", parse_mode=ParseMode.MARKDOWN_V2)
            except Exception: pass
            
            text_to_admins = f"🔔 *طلب انضمام جديد\\!*\n\n👤 *الاسم:* {escape_markdown_v2(user.first_name or 'N/A')}\n"
            if user.last_name: text_to_admins += f"📎 *اللقب:* {escape_markdown_v2(user.last_name)}\n"
            text_to_admins += f"🆔 *الـ ID:* `{user_id}`\n"
            if user.username: text_to_admins += f"🌐 *اليوزر:* @{escape_markdown_v2(user.username)}\n"
            if user.language_code: text_to_admins += f"🌍 *اللغة:* {escape_markdown_v2(user.language_code)}\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"accept_req:{user_id}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"reject_req:{user_id}")]
            ])
            
            admins = await access_manager.get_admins()
            for admin_id in admins:
                try: 
                    msg = await context.bot.send_message(
                        chat_id=int(admin_id), 
                        text=text_to_admins, 
                        parse_mode=ParseMode.MARKDOWN_V2, 
                        reply_markup=keyboard
                    )
                    await access_manager.track_request(user_id, int(admin_id), msg.message_id)
                except Exception as e: 
                    logger.warning(f"Could not send join request to admin {admin_id}: {e}")
            
            await access_manager.update_cooldown(user_id)
    
    raise ApplicationHandlerStop