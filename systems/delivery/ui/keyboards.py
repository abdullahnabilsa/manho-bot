# File: systems/delivery/ui/keyboards.py
from __future__ import annotations
from typing import List, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="open_settings")],
        [InlineKeyboardButton("📖 المساعدة", callback_data="open_help")]
    ])

def get_persistent_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("⚙️ الإعدادات"), KeyboardButton("📖 المساعدة")],
            [KeyboardButton("🟢 بدء الجلسة"), KeyboardButton("🔴 إنهاء الجلسة")]
        ],
        resize_keyboard=True
    )

def get_session_tracker_keyboard() -> InlineKeyboardMarkup:
    """Interactive keyboard attached to the live session tracker."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة ملاحظة", callback_data="add_note_prompt")],
        [
            InlineKeyboardButton("🔴 إنهاء الجلسة", callback_data="end_session_inline"),
            InlineKeyboardButton("🚫 إلغاء الجلسة", callback_data="cancel_session_inline")
        ]
    ])

def get_settings_dashboard_keyboard(user_settings: dict) -> InlineKeyboardMarkup:
    persona = user_settings.get("persona", "Default Translator")
    mode = "رسالة موحدة" if user_settings.get("mode") == "single_message" else "فصل المشاهد"
    output_method = user_settings.get("output_method", "files_only")
    if output_method == "chat_and_files":
        output_method = "messages_and_files"
    output_display = "رسائل وملفات" if output_method == "messages_and_files" else ("رسائل فقط" if output_method == "messages_only" else "ملفات فقط")
    fmt = user_settings.get("file_format", "docx").upper()
    session_mode = user_settings.get("session_mode", "grouped")
    session_display = "فردي (ملف لكل صورة)" if session_mode == "individual" else "موحد (ملف واحد)"
    use_glossary = user_settings.get("use_glossary", "false")
    glossary_display = "مفعل ✅" if use_glossary == "true" else "معطل ❌"
    
    keyboard = [
        [InlineKeyboardButton(f"🎭 المترجم: {persona}", callback_data="open_personas")],
        [InlineKeyboardButton(f"📨 تقسيم الرسائل: {mode}", callback_data="open_delivery_mode")],
        [InlineKeyboardButton(f"📤 طريقة الإخراج: {output_display}", callback_data="open_output_method")],
        [InlineKeyboardButton(f"📄 صيغة الملفات: {fmt}", callback_data="open_file_format")],
        [InlineKeyboardButton(f"📦 وضع التجميع: {session_display}", callback_data="open_session_mode")],
        [InlineKeyboardButton(f"📚 القاموس: {glossary_display}", callback_data="toggle_glossary")],
        [InlineKeyboardButton("🔐 مفتاح API الخاص", callback_data="open_api_key")],
        [InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="back_to_main")]
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
        [InlineKeyboardButton("✅ رسالة موحدة لكل صفحة" if current_mode == "single_message" else "⬜ رسالة موحدة لكل صفحة", callback_data="set_mode_single_message")],
        [InlineKeyboardButton("✅ فصل المشاهد لكل صفحة" if current_mode == "scene_split" else "⬜ فصل المشاهد لكل صفحة", callback_data="set_mode_scene_split")],
        [InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_output_method_keyboard(current_method: str) -> InlineKeyboardMarkup:
    if current_method == "chat_and_files":
        current_method = "messages_and_files"
    keyboard = [
        [InlineKeyboardButton("✅ رسائل فقط" if current_method == "messages_only" else "⬜ رسائل فقط", callback_data="set_output_messages_only")],
        [InlineKeyboardButton("✅ ملفات فقط" if current_method == "files_only" else "⬜ ملفات فقط", callback_data="set_output_files_only")],
        [InlineKeyboardButton("✅ رسائل وملفات" if current_method == "messages_and_files" else "⬜ رسائل وملفات", callback_data="set_output_messages_and_files")],
        [InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_file_format_keyboard(current_fmt: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✅ TXT" if current_fmt == "txt" else "⬜ TXT", callback_data="set_fmt_txt")],
        [InlineKeyboardButton("✅ DOCX (Word)" if current_fmt == "docx" else "⬜ DOCX (Word)", callback_data="set_fmt_docx")],
        [InlineKeyboardButton("✅ TXT و DOCX" if current_fmt == "both" else "⬜ TXT و DOCX", callback_data="set_fmt_both")],
        [InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_session_mode_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✅ موحد (ملف واحد للجلسة)" if current_mode == "grouped" else "⬜ موحد (ملف واحد للجلسة)", callback_data="set_session_grouped")],
        [InlineKeyboardButton("✅ فردي (ملف لكل صورة)" if current_mode == "individual" else "⬜ فردي (ملف لكل صورة)", callback_data="set_session_individual")],
        [InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="open_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_paginated_keyboard(
    items: List[Tuple[str, str]],
    action: str,
    page: int = 0,
    items_per_page: int = 8
) -> InlineKeyboardMarkup:
    total_items = len(items)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = items[start_idx:end_idx]
    
    keyboard = []
    
    for display_text, target_id in page_items:
        keyboard.append([
            InlineKeyboardButton(
                display_text,
                callback_data=f"adm_sel_{action}_{target_id}"
            )
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ السابق", callback_data=f"adm_nav_{action}_{page - 1}")
        )
    
    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="adm_nopage")
        )
    
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("التالي ➡️", callback_data=f"adm_nav_{action}_{page + 1}")
        )
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("❌ إلغاء", callback_data="adm_cancel")])
    
    return InlineKeyboardMarkup(keyboard)

def build_confirmation_keyboard(action: str, target_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد", callback_data=f"adm_conf_{action}_{target_id}"),
            InlineKeyboardButton("❌ إلغاء", callback_data="adm_cancel")
        ]
    ])