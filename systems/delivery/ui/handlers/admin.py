# File: systems/delivery/ui/handlers/admin.py
from __future__ import annotations
import logging
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from utils.markdown_escaper import escape_markdown_v2
from systems.delivery.ui.keyboards import build_paginated_keyboard, build_confirmation_keyboard

logger = logging.getLogger(__name__)

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    container = context.bot_data["container"]
    is_adm = await container.access.is_admin(update.effective_user.id)
    if not is_adm:
        if update.message:
            await update.message.reply_text("🚫 *هذا الأمر مخصص للمشرفين فقط\\.*", parse_mode=ParseMode.MARKDOWN_V2)
        elif update.callback_query:
            await update.callback_query.answer("🚫 للمشرفين فقط", show_alert=True)
    return is_adm

async def add_public_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context): return
    context.user_data['awaiting_admin_api_key'] = True
    await update.message.reply_text(
        "👑 *إضافة مفتاح API عام*\nأرسل المفتاح الآن ليتم إضافته لقاعدة البيانات واستخدامه كمفتاح احتياطي للمستخدمين\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def receive_admin_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['awaiting_admin_api_key'] = False
    key = update.message.text.strip()
    container = context.bot_data["container"]
    added = await container.api_keys.add_public_key(key)
    if added:
        await update.message.reply_text(
            "✅ *تمت الإضافة*\nتم إضافة المفتاح العام إلى قاعدة البيانات بنجاح\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            "ℹ️ *معلومة*\nهذا المفتاح مسجل مسبقاً في النظام\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def list_public_keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context): return
    container = context.bot_data["container"]
    keys = await container.api_keys.get_public_keys()
    if not keys:
        await update.message.reply_text(
            "📭 *لا توجد مفاتيح*\nلم يتم تسجيل أي مفاتيح عامة بعد\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    text = "📋 *المفاتيح العامة المسجلة:*\n\n"
    for i, k in enumerate(keys, 1):
        masked = escape_markdown_v2(k[:8] + "..." + k[-4:])
        text += f"{i}\\. `{masked}`\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

async def remove_public_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context): return
    container = context.bot_data["container"]
    keys = await container.api_keys.get_public_keys()
    
    if not keys:
        await update.message.reply_text(
            "📭 *لا توجد مفاتيح*\nلم يتم تسجيل أي مفاتيح عامة بعد\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    args = context.args
    if not args:
        items = [(f"🔑 {k[:8]}...{k[-4:]}", k[:12]) for k in keys]
        keyboard = build_paginated_keyboard(items, "apikey_removekey", page=0)
        await update.message.reply_text(
            "🗑️ *حذف مفتاح API عام*\n\nاختر المفتاح من القائمة:",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return
    
    prefix = args[0]
    found_key = None
    for k in keys:
        if k.startswith(prefix):
            found_key = k
            break
    if found_key:
        await container.api_keys.remove_public_key(found_key)
        masked = escape_markdown_v2(found_key[:8] + "..." + found_key[-4:])
        await update.message.reply_text(
            f"🗑️ *تم الحذف*\nتمت إزالة المفتاح `{masked}` من النظام\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            "⚠️ *غير موجود*\nلا يوجد مفتاح يبدأ بالأحرف التي أدخلتها\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def handle_apikey_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    data = query.data or ""
    
    if not await container.access.is_admin(query.from_user.id):
        await query.answer("🚫 للمشرفين فقط", show_alert=True)
        return
    
    if data.startswith("adm_sel_apikey_"):
        parts = data.replace("adm_sel_apikey_", "").rsplit("_", 1)
        if len(parts) != 2: return
        action, target_prefix = parts
        
        if action == "removekey":
            keys = await container.api_keys.get_public_keys()
            found_key = next((k for k in keys if k.startswith(target_prefix)), None)
            if not found_key:
                await query.answer("⚠️ المفتاح غير موجود.", show_alert=True)
                return
            
            masked = escape_markdown_v2(found_key[:8] + "..." + found_key[-4:])
            keyboard = build_confirmation_keyboard(f"apikey_{action}", target_prefix)
            await query.edit_message_text(
                f"🗑️ *تأكيد حذف المفتاح*\n\n"
                f"🔑 *المفتاح:* `{masked}`\n\n"
                f"⚠️ سيتم حذف هذا المفتاح نهائياً\\.\n"
                f"_هل أنت متأكد؟_",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
    
    elif data.startswith("adm_conf_apikey_"):
        parts = data.replace("adm_conf_apikey_", "").rsplit("_", 1)
        if len(parts) != 2: return
        action, target_prefix = parts
        
        if action == "removekey":
            keys = await container.api_keys.get_public_keys()
            found_key = next((k for k in keys if k.startswith(target_prefix)), None)
            if not found_key:
                await query.edit_message_text(
                    "⚠️ *غير موجود*\nالمفتاح لم يعد موجوداً\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return
            
            await container.api_keys.remove_public_key(found_key)
            masked = escape_markdown_v2(found_key[:8] + "..." + found_key[-4:])
            await query.edit_message_text(
                f"🗑️ *تم الحذف*\nتمت إزالة المفتاح `{masked}` من النظام\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    
    elif data.startswith("adm_nav_apikey_"):
        parts = data.replace("adm_nav_apikey_", "").rsplit("_", 1)
        if len(parts) != 2: return
        action, page_str = parts
        if not page_str.isdigit(): return
        page = int(page_str)
        
        if action == "removekey":
            keys = await container.api_keys.get_public_keys()
            items = [(f"🔑 {k[:8]}...{k[-4:]}", k[:12]) for k in keys]
            
            if not items:
                try:
                    await query.edit_message_text("⚠️ لا توجد مفاتيح لعرضها\\.", parse_mode=ParseMode.MARKDOWN_V2)
                except Exception:
                    pass
                return
            
            keyboard = build_paginated_keyboard(items, f"apikey_{action}", page=page)
            try:
                await query.edit_message_text(
                    "🗑️ *حذف مفتاح API عام*\n\nاختر المفتاح من القائمة:",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=keyboard
                )
            except Exception:
                pass

async def handle_admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_text(
            "❌ *تم إلغاء العملية\\.*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception:
        pass

async def upload_dict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context): return
    context.user_data['awaiting_glossary_upload'] = True
    await update.message.reply_text(
        "📚 *رفع قاموس المصطلحات*\n\n"
        "يرجى إرسال ملف بصيغة `.txt` يحتوي على JSON صالح\\.\n"
        "التنسيق المطلوب: `{\"كلمة_أجنبية\": \"الترجمة_العربية\"}`\\.\n\n"
        "⚠️ سيتم استبدال القاموس الحالي بالكامل\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def download_dict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context): return
    container = context.bot_data["container"]
    file_path = container.glossary.get_file_path()
    try:
        with open(file_path, "rb") as f:
            await update.message.reply_document(
                document=InputFile(f, filename="glossary.txt"),
                caption="📥 *قاموس المصطلحات الحالي*\nيمكنك تعديله وإعادة رفعه عبر الأمر `/uploaddict`\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    except Exception as e:
        logger.error(f"Failed to send glossary: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء محاولة إرسال ملف القاموس\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )