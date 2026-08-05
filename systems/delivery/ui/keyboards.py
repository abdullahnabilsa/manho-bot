# File: systems/delivery/ui/keyboards.py
from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="open_settings")],
        [InlineKeyboardButton("📖 كيفية الاستخدام", callback_data="open_help")]
    ])

def get_persistent_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("⚙️ الإعدادات"), KeyboardButton("📖 المساعدة")],
            [KeyboardButton("🟢 بدء الجلسة"), KeyboardButton("🔴 إنهاء الجلسة")]
        ],
        resize_keyboard=True
    )

def get_settings_dashboard_keyboard(user_settings: dict) -> InlineKeyboardMarkup:
    persona = user_settings.get("persona", "Default Translator")
    mode = "رسالة موحدة" if user_settings.get("mode") == "single_message" else "فصل المشاهد"
    output_method = user_settings.get("output_method", "files_only")
    if output_method == "chat_and_files":
        output_method = "messages_and_files"
    output_display = "رسائل وملفات" if output_method == "messages_and_files" else ("رسائل تلجرام فقط" if output_method == "messages_only" else "ملفات فقط")
    fmt = user_settings.get("file_format", "docx").upper()
    session_mode = user_settings.get("session_mode", "grouped")
    session_display = "تجميع فردي" if session_mode == "individual" else "تجميع جماعي"
    use_glossary = user_settings.get("use_glossary", "false")
    glossary_display = "مفصل ❌" if use_glossary == "false" else "مفعل ✅"
    
    keyboard = [
        [InlineKeyboardButton(f"🎭 المترجم: {persona}", callback_data="open_personas")],
        [InlineKeyboardButton(f"📨 الإرسال: {mode}", callback_data="open_delivery_mode")],
        [InlineKeyboardButton(f"📤 الإخراج: {output_display}", callback_data="open_output_method")],
        [InlineKeyboardButton(f"📄 الصيغة: {fmt}", callback_data="open_file_format")],
        [InlineKeyboardButton(f"📦 وضع الجلسة: {session_display}", callback_data="open_session_mode")],
        [InlineKeyboardButton(f"📚 القاموس: {glossary_display}", callback_data="toggle_glossary")],
        [InlineKeyboardButton("🔐 مفتاح API الخاص", callback_data="open_api_key")],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_personas_keyboard(personas: list[str], current_persona: str) -> InlineKeyboardMarkup:
    keyboard = []
    for persona in personas:
        prefix = "✅ " if persona == current_persona else "⬜ "
        keyboard.append([InlineKeyboardButton(f"{prefix}{persona}", callback_data=f"set_persona_{persona}")])
    keyboard.append([InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")])
    return InlineKeyboardMarkup(keyboard)

def get_delivery_mode_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✅ رسالة موحدة" if current_mode == "single_message" else "⬜ رسالة موحدة", callback_data="set_mode_single_message")],
        [InlineKeyboardButton("✅ فصل المشاهد" if current_mode == "scene_split" else "⬜ فصل المشاهد", callback_data="set_mode_scene_split")],
        [InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_output_method_keyboard(current_method: str) -> InlineKeyboardMarkup:
    if current_method == "chat_and_files":
        current_method = "messages_and_files"
    keyboard = [
        [InlineKeyboardButton("✅ رسائل تلجرام فقط" if current_method == "messages_only" else "⬜ رسائل تلجرام فقط", callback_data="set_output_messages_only")],
        [InlineKeyboardButton("✅ ملفات فقط" if current_method == "files_only" else "⬜ ملفات فقط", callback_data="set_output_files_only")],
        [InlineKeyboardButton("✅ رسائل وملفات" if current_method == "messages_and_files" else "⬜ رسائل وملفات", callback_data="set_output_messages_and_files")],
        [InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_file_format_keyboard(current_fmt: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✅ TXT" if current_fmt == "txt" else "⬜ TXT", callback_data="set_fmt_txt")],
        [InlineKeyboardButton("✅ DOCX (Word)" if current_fmt == "docx" else "⬜ DOCX (Word)", callback_data="set_fmt_docx")],
        [InlineKeyboardButton("✅ كلاهما" if current_fmt == "both" else "⬜ كلاهما", callback_data="set_fmt_both")],
        [InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_session_mode_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✅ تجميع جماعي (ملف واحد)" if current_mode == "grouped" else "⬜ تجميع جماعي (ملف واحد)", callback_data="set_session_grouped")],
        [InlineKeyboardButton("✅ تجميع فردي (ملف لكل صورة)" if current_mode == "individual" else "⬜ تجميع فردي (ملف لكل صورة)", callback_data="set_session_individual")],
        [InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)