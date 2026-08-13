# File: systems/delivery/ui/handlers/api_keys.py
from __future__ import annotations
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.markdown_escaper import escape_markdown_v2

def mask_key(key: str) -> str:
    if not key or len(key) < 12: return "Invalid Key"
    return escape_markdown_v2(key[:10] + "..." + key[-4:])

async def api_key_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    user_key = await container.api_keys.get_user_key(query.from_user.id)
    
    text = "🔐 *إدارة مفتاح API الخاص*\n\n"
    if user_key:
        text += f"✅ *الحالة:* تستخدم مفتاحك الخاص\\.\n"
        text += f"🔑 *المفتاح الحالي:* `{mask_key(user_key)}`\n\n"
        text += "يُستخدم مفتاحك حصرياً لترجماتك لضمان أقصى سرعة واستقرار ممكن\\.\n"
        text += "للعودة لاستخدام المفاتيح العامة للبوت، يمكنك حذف مفتاحك\\."
    else:
        public_keys = await container.api_keys.get_public_keys()
        text += f"🌐 *الحالة:* تستخدم المفاتيح العامة للبوت \\({len(public_keys)} مفتاح متاح\\)\\.\n\n"
        text += "يمكنك إضافة مفتاح API الخاص بك من Google AI Studio لضمان استقرار الترجمة وعدم التأثر بازدحام المستخدمين الآخرين\\."
        
    keyboard = [
        [InlineKeyboardButton("➕ إضافة مفتاح خاص", callback_data="add_user_api_key")],
    ]
    if user_key:
        keyboard.append([InlineKeyboardButton("❌ حذف المفتاح والعودة للعامة", callback_data="del_user_api_key")])
    keyboard.append([InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")])
    
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup(keyboard))

async def add_user_api_key_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data['awaiting_user_api_key'] = True
    await query.edit_message_text(
        "🔑 *إضافة مفتاح API*\n\nأرسل مفتاح الـ API الخاص بك الآن كرسالة نصية واحدة\\.\n\n_سيتم حفظه بأمان واستخدامه حصرياً لحسابك\\._", 
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def receive_user_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['awaiting_user_api_key'] = False
    key = update.message.text.strip()
    container = context.bot_data["container"]
    await container.api_keys.set_user_key(update.effective_user.id, key)
    await update.message.reply_text(
        "✅ *تم الحفظ بنجاح\\!*\nتم تفعيل مفتاحك الخاص\\. سيتم استخدامه في ترجماتك القادمة فوراً\\.", 
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def del_user_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    removed = await container.api_keys.remove_user_key(query.from_user.id)
    if removed:
        await query.edit_message_text(
            "🗑️ *تم الحذف\\.*\nتم حذف مفتاحك الخاص\\. ستعود الآن لاستخدام المفاتيح العامة للبوت تلقائياً\\.", 
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await query.edit_message_text(
            "⚠️ *لا يوجد مفتاح خاص بك لحذفه\\.*", 
            parse_mode=ParseMode.MARKDOWN_V2
        )