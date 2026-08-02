# systems/delivery/ui/handlers/admin.py
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.markdown_escaper import escape_markdown_v2

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    container = context.bot_data["container"]
    is_adm = await container.access.is_admin(update.effective_user.id)
    if not is_adm:
        if update.message:
            await update.message.reply_text("🚫 هذا الأمر مخصص للمشرفين فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        elif update.callback_query:
            await update.callback_query.answer("🚫 للمشرفين فقط", show_alert=True)
    return is_adm

async def add_public_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context): return
    context.user_data['awaiting_admin_api_key'] = True
    await update.message.reply_text("👑 *إضافة مفتاح عام*\nأرسل مفتاح الـ API العام الآن ليتم إضافته للبوت\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def receive_admin_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['awaiting_admin_api_key'] = False
    key = update.message.text.strip()
    container = context.bot_data["container"]
    added = await container.api_keys.add_public_key(key)
    if added:
        await update.message.reply_text("✅ *نجحت العملية*\nتم إضافة المفتاح العام إلى قاعدة البيانات\\.", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text("ℹ️ *معلومات*\nهذا المفتاح مسجل مسبقاً في النظام\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def list_public_keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context): return
    container = context.bot_data["container"]
    keys = await container.api_keys.get_public_keys()
    if not keys:
        await update.message.reply_text("📭 *لا توجد مفاتيح*\nلم يتم تسجيل أي مفاتيح عامة بعد\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    text = "📋 *المفاتيح العامة المسجلة:*\n\n"
    for i, k in enumerate(keys, 1):
        masked = escape_markdown_v2(k[:8] + "..." + k[-4:])
        text += f"{i}\\. `{masked}`\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

async def remove_public_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context): return
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ *الاستخدام غير صحيح*\nالصيغة: `/removekey <أول 8 أحرف من المفتاح>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    prefix = args[0]
    container = context.bot_data["container"]
    keys = await container.api_keys.get_public_keys()
    found_key = None
    for k in keys:
        if k.startswith(prefix):
            found_key = k
            break
    if found_key:
        await container.api_keys.remove_public_key(found_key)
        masked = escape_markdown_v2(found_key[:8] + "..." + found_key[-4:])
        await update.message.reply_text(f"🗑️ *تم الحذف*\nتمت إزالة المفتاح `{masked}` من النظام\\.", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text("⚠️ *غير موجود*\nلا يوجد مفتاح يبدأ بالأحرف التي أدخلتها\\.", parse_mode=ParseMode.MARKDOWN_V2)