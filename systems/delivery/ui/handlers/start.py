# systems/delivery/ui/handlers/start.py
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
        "👋 *أهلاً بك في بوت الترجمة الاحترافي للمانغا والمانهوا\\!* \n\n"
        "أداة متقدمة تعتمد على الذكاء الاصطناعي لاستخراج النصوص من الصور وترجمتها بدقة عالية\\.\n\n"
        "📌 *كيف تبدأ:*\n"
        "1\\. اضغط زر *🟢 بدء الجلسة* في الأسفل\n"
        "2\\. أرسل صور صفحات المانغا دفعة واحدة أو واحدة تلو الأخرى *\\(لا يوجد حد أقصى\\)*\n"
        "3\\. اضغط زر *🔴 إنهاء الجلسة* لتجميع كل الصور في ملف واحد\\.\n\n"
        "💡 *ميزات البوت:*\n"
        "• دعم عدة أساليب ترجمة \\(المترجم الافتراضي، اللوحات، NABIL\\)\n"
        "• إمكانية استخدام مفتاح API الخاص بك للسرعة القصوى\n"
        "• إخراج النتائج كرسائل تلجرام أو ملفات Word/TXT\n\n"
        "🚪 *ملاحظة:* يمكنك إرسال الأمر `/cancel` في أي وقت لإلغاء الجلسة الحالية والخروج منها\\.\n\n"
        "⚙️ يمكنك تخصيص التجربة من زر *الإعدادات*\\."
    )
    await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_persistent_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 *دليل الاستخدام الشامل*\n\n"
        "⚙️ *لوحة الإعدادات تتيح لك التحكم في:*\n"
        "1\\. *🎭 المترجم:* اختيار أسلوب الترجمة وهيكل البيانات\\.\n"
        "2\\. *📨 الإرسال:* رسالة موحدة لكل صفحة، أو فصل المشاهد\\.\n"
        "3\\. *📤 الإخراج:* استلام الترجمة في الشات فقط، ملفات فقط، أو كلاهما\\.\n"
        "4\\. *📄 الصيغة:* اختيار صيغة الملفات \\(TXT أو DOCX\\)\\.\n"
        "5\\. *🔐 مفتاح API:* إضافة مفتاحك الخاص لاستخدامه حصرياً\\.\n\n"
        "📦 *نظام الجلسات:*\n"
        "الجلسة تتيح لك إرسال عدد كبير من الصور \\(50 أو أكثر\\) دفعة واحدة، ويقوم البوت بمعالجتها بصمت في الطابور\\. "
        "عند ضغطك على *إنهاء الجلسة*، يتم دمج كل الصور المترجمة في ملف واحد مرتب\\.\n\n"
        "🚪 *إلغاء الجلسة:*\n"
        "إذا أردت إيقاف الجلسة والخروج منها في أي وقت \\(حتى أثناء كتابة اسم الملف\\)، فقط أرسل الأمر `/cancel`\\.\n\n"
        "⏳ *ملاحظة حول الطابور:*\n"
        "يتم معالجة الصور بالتتابع لضمان الجودة\\. ستظهر لك رسالة متحركة تخبرك بمكانك في الطابور والصور المترجمة\\."
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard())
    else:
        await update.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=get_persistent_keyboard())