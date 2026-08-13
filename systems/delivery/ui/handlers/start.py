# File: systems/delivery/ui/handlers/start.py
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from systems.delivery.ui.keyboards import get_main_menu_keyboard, get_persistent_keyboard

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    user_id = update.effective_user.id
    user_settings = await container.settings.get_user_settings(user_id)
    if not user_settings.get("persona"):
        await container.settings.set_persona(user_id, "Default Translator")

    text = (
        "👋 *أهلاً بك في نظام الترجمة الآلي للمانغا والمانهوا\\.*\n\n"
        "منصة احترافية تعتمد على الذكاء الاصطناعي لاستخراج النصوص وترجمتها بدقة عالية\\.\n\n"
        "📌 *كيف تبدأ:*\n"
        "1\\. اضغط زر *🟢 بدء الجلسة* في الأسفل\\.\n"
        "2\\. أرسل صور صفحات المانغا دفعة واحدة أو تباعاً\\.\n"
        "3\\. اضغط زر *🔴 إنهاء الجلسة* لتجميع الصور وبدء الترجمة\\.\n\n"
        "💡 *أبرز الميزات:*\n"
        "• أساليب ترجمة متعددة \\(افتراضي، لوحات، نص خام\\)\\.\n"
        "• إمكانية استخدام مفتاح API الخاص بك لسرعة استثنائية\\.\n"
        "• إخراج النتائج كرسائل أو ملفات \\(Word/TXT\\)\\.\n"
        "• دعم *قاموس مصطلحات مخصص* لتوحيد الترجمة\\.\n\n"
        "⚙️ يمكنك تخصيص تجربتك من زر *الإعدادات*\\.\n"
        "🚪 لإلغاء الجلسة في أي وقت، أرسل: `/cancel`"
    )
    await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_persistent_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 *دليل الاستخدام الشامل*\n\n"
        "⚙️ *لوحة الإعدادات:*\n"
        "• *🎭 المترجم:* أسلوب استخراج وترجمة النصوص\\.\n"
        "• *📨 الإرسال:* طريقة تقسيم الرسائل \\(موحدة أو فصل مشاهد\\)\\.\n"
        "• *📤 الإخراج:* استلام الترجمة كرسائل، ملفات، أو كليهما\\.\n"
        "• *📄 الصيغة:* صيغة ملفات التحميل \\(TXT أو DOCX\\)\\.\n"
        "• *📦 وضع الجلسة:* موحد \\(ملف واحد\\) أو فردي \\(ملف لكل صورة\\)\\.\n"
        "• *📚 القاموس:* تفعيل أو تعطيل قاموس المصطلحات المخصص\\.\n"
        "• *🔐 مفتاح API:* استخدام مفتاحك الخاص لسرعة استثنائية\\.\n\n"
        "📦 *نظام الجلسات:*\n"
        "يسمح لك بإرسال عدد كبير من الصور دفعة واحدة\\. يعالج البوت الصور بصمت في الطابور، وعند إنهاء الجلسة يتم دمجها \\(في الوضع الموحد\\) وإرسالها\\.\n\n"
        "📚 *قاموس المصطلحات:*\n"
        "يمكن للمشرفين رفع قاموس عبر `/uploaddict` \\(ملف JSON بصيغة txt\\)\\. فعّله من الإعدادات لفرض استخدام مصطلحات محددة\\.\n\n"
        "⏳ *ملاحظة حول الطابور:*\n"
        "يعمل النظام بعدد ثابت من العمال المتوازيين لضمان الجودة وعدم التحميل الزائد\\. ستظهر لك رسالة متحركة تعرض تقدم الجلسة وعدد الصور المترجمة\\.\n\n"
        "🚪 *إلغاء الجلسة:*\n"
        "لإيقاف الجلسة والخروج منها في أي وقت \\(حتى أثناء كتابة الاسم\\)، أرسل الأمر: `/cancel`"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard())
    else:
        await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_persistent_keyboard())