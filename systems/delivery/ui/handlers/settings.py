# File: systems/delivery/ui/handlers/settings.py
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from systems.delivery.ui.keyboards import (
    get_settings_dashboard_keyboard, get_personas_keyboard, get_delivery_mode_keyboard,
    get_output_method_keyboard, get_file_format_keyboard, get_main_menu_keyboard,
    get_session_mode_keyboard
)
from utils.markdown_escaper import escape_markdown_v2
from systems.delivery.ui.handlers.api_keys import api_key_menu, add_user_api_key_start, del_user_api_key

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_settings = await container.settings.get_user_settings(update.effective_user.id)
    persona = user_settings.get('persona') or "Default Translator"
    mode = user_settings.get('mode', 'scene_split')
    output_method = user_settings.get('output_method', 'files_only')
    file_format = user_settings.get('file_format', 'docx')
    session_mode = user_settings.get('session_mode', 'grouped')
    
    mode_display = "رسالة موحدة" if mode == "single_message" else "فصل المشاهد"
    if output_method == "chat_and_files":
        output_method = "messages_and_files"
    output_display = "رسائل وملفات" if output_method == "messages_and_files" else ("رسائل تلجرام فقط" if output_method == "messages_only" else "ملفات فقط")
    file_fmt_escaped = escape_markdown_v2(file_format.upper())
    session_display = "تجميع فردي" if session_mode == "individual" else "تجميع جماعي"
    
    text = (
        "⚙️ *لوحة التحكم الرئيسية*\n\n"
        "إليك إعداداتك الحالية\\. اضغط على أي خيار لتعديله:\n\n"
        f"🎭 *المترجم الحالي:* {escape_markdown_v2(persona)}\n"
        f"📨 *نمط الإرسال:* {escape_markdown_v2(mode_display)}\n"
        f"📤 *طريقة الإخراج:* {escape_markdown_v2(output_display)}\n"
        f"📄 *صيغة الملفات:* {file_fmt_escaped}\n"
        f"📦 *وضع الجلسة:* {escape_markdown_v2(session_display)}\n\n"
        "_اضغط على الأزرار أدناه للتعديل_"
    )
    markup = get_settings_dashboard_keyboard(user_settings)
    if update.callback_query:
        # تم إزالة الاستدعاء المزدوج لـ answer() هنا لمنع تعطل المعالج
        await update.callback_query.edit_message_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup)
    else:
        await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=markup)

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    container = context.bot_data["container"]
    user_id = query.from_user.id

    if data == "open_settings":
        await settings_command(update, context)
    elif data == "open_api_key":
        await api_key_menu(update, context)
    elif data == "add_user_api_key":
        await add_user_api_key_start(update, context)
    elif data == "del_user_api_key":
        await del_user_api_key(update, context)
    elif data == "open_personas":
        personas = container.personas.get_available_personas()
        current = (await container.settings.get_user_settings(user_id)).get("persona")
        await query.edit_message_text("🎭 *اختيار المترجم*\n\nاختر أسلوب الترجمة الذي يناسب عملك:", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_personas_keyboard(personas, current))
    elif data == "open_delivery_mode":
        current = (await container.settings.get_user_settings(user_id)).get("mode")
        await query.edit_message_text("📨 *وضع الإرسال*\n\nحدد كيف تريد تقسيم الرسائل:", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_delivery_mode_keyboard(current))
    elif data == "open_output_method":
        current = (await container.settings.get_user_settings(user_id)).get("output_method")
        await query.edit_message_text("📤 *طريقة الإخراج*\n\nكيف تريد استلام الترجمة النهائية؟", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_output_method_keyboard(current))
    elif data == "open_file_format":
        current = (await container.settings.get_user_settings(user_id)).get("file_format")
        await query.edit_message_text("📄 *صيغة الملفات*\n\nاختر صيغة ملفات التحميل:", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_file_format_keyboard(current))
    elif data == "open_session_mode":
        current = (await container.settings.get_user_settings(user_id)).get("session_mode")
        await query.edit_message_text("📦 *وضع الجلسة*\n\nاختر طريقة تجميع ملفات الترجمة عند إرسال الصور:", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_session_mode_keyboard(current))
    elif data.startswith("set_persona_"):
        await container.settings.set_persona(user_id, data.replace("set_persona_", ""))
        await settings_command(update, context)
    elif data == "set_mode_single_message":
        await container.settings.set_delivery_mode(user_id, "single_message")
        await settings_command(update, context)
    elif data == "set_mode_scene_split":
        await container.settings.set_delivery_mode(user_id, "scene_split")
        await settings_command(update, context)
    elif data == "set_output_messages_only":
        await container.settings.set_output_method(user_id, "messages_only")
        await settings_command(update, context)
    elif data == "set_output_files_only":
        await container.settings.set_output_method(user_id, "files_only")
        await settings_command(update, context)
    elif data == "set_output_messages_and_files":
        await container.settings.set_output_method(user_id, "messages_and_files")
        await settings_command(update, context)
    elif data == "set_fmt_txt":
        await container.settings.set_file_format(user_id, "txt")
        await settings_command(update, context)
    elif data == "set_fmt_docx":
        await container.settings.set_file_format(user_id, "docx")
        await settings_command(update, context)
    elif data == "set_fmt_both":
        await container.settings.set_file_format(user_id, "both")
        await settings_command(update, context)
    elif data == "set_session_grouped":
        await container.settings.set_session_mode(user_id, "grouped")
        await settings_command(update, context)
    elif data == "set_session_individual":
        await container.settings.set_session_mode(user_id, "individual")
        await settings_command(update, context)
    elif data == "open_help":
        from systems.delivery.ui.handlers.start import help_command
        await help_command(update, context)
    elif data == "back_to_main":
        await query.edit_message_text("🏠 *القائمة الرئيسية*\n\nاستخدم الأزرار بالأسفل للتحكم في البوت\\.", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard())