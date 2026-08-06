# systems/delivery/ui/handlers/concurrency.py
from __future__ import annotations
import asyncio
import logging
import time as _time
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from utils.markdown_escaper import escape_markdown_v2
from systems.delivery.ui.keyboards import build_boost_keyboard, build_setlimit_keyboard, build_boost_limit_keyboard

logger = logging.getLogger(__name__)

async def boost_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    container = context.bot_data["container"]
    
    max_boost_limit = await container.concurrency.get_max_boost_limit()
    if max_boost_limit <= 1:
        await update.message.reply_text(
            "⚠️ *المعالجة المتوازية غير متاحة حالياً*\n"
            "السوبر أدمن لم يقم بتفعيل سقف التعزيز بعد\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Check permanent access
    access = await container.concurrency.check_user_access(user.id)
    if access == "permanent":
        await update.message.reply_text(
            "ℹ️ *لديك صلاحية المعالجة المتوازية الدائمة\\.*\n"
            "لا تحتاج لطلب تعزيز مؤقت\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Check if already boosting
    active = await container.concurrency._db_store.get_active_boost()
    if active and active[0] == user.id and active[2] > 0:
        if _time.time() < active[2]:
            await update.message.reply_text(
                "ℹ️ أنت تستخدم المعالجة المتوازية حالياً بالفعل\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
    
    # Check if occupied by another user
    if active and _time.time() < active[2]:
        active_user = escape_markdown_v2(active[1] or str(active[0]))
        await update.message.reply_text(
            f"⏳ *المعالجة المتوازية مستخدمة حالياً*\n\n"
            f"المستخدم {active_user} يستخدمها الآن\\.\n"
            f"سيتم إعلامك فور انتهاء دورهم\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Check cooldown
    cooldown_until = await container.concurrency._db_store.get_cooldown(user.id)
    if cooldown_until and _time.time() < cooldown_until:
        remaining = cooldown_until - _time.time()
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        await update.message.reply_text(
            f"⏳ *انتهى دورك للتو*\n\n"
            f"يرجى الانتظار {mins} دقيقة و {secs} ثانية قبل أن تتمكن من استخدامها مرة أخرى\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Show boost selection keyboard
    await update.message.reply_text(
        f"🚀 *طلب التعزيز المؤقت*\n\n"
        f"الحد الأقصى المتاح للتعزيز: `{max_boost_limit}` عمال متوازيين\n"
        f"اختر عدد العمال المطلوب \\(سيستمر لمدة 10 دقائق\\):\n\n"
        f"⚠️ _لإيقاف التعزيز يدوياً، أرسل `/unboost`_",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=build_boost_keyboard(max_boost_limit)
    )

async def handle_boost_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    user = query.from_user
    
    data = query.data or ""
    # boost_req_<count>
    count_str = data.replace("boost_req_", "")
    if not count_str.isdigit():
        return
    count = int(count_str)
    
    # Strict validation against the current max_boost_limit from DB
    max_boost_limit = await container.concurrency.get_max_boost_limit()
    if count < 2 or count > max_boost_limit:
        await query.edit_message_text(
            "⚠️ *طلب غير صالح*\n"
            "تم تجاوز الحد الأقصى المسموح للتعزيز\\. ربما قام المشرف بتخفيض السقف\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    username = f"@{user.username}" if user.username else user.first_name
    result = await container.concurrency.request_boost(user.id, username, count)
    
    if result["status"] == "granted":
        asyncio.create_task(container.concurrency.auto_expire_boost(user.id, context.bot))
        await query.edit_message_text(
            f"🚀 *تم تفعيل التعزيز المؤقت\\!*\n\n"
            f"عدد العمال: `{count}` ⚡\n"
            f"لديك الآن *10 دقائق* لمعالجة صورك بالتوازي\\. أرسل صورك الآن دفعة واحدة\\!\n\n"
            f"لإيقاف التعزيز يدوياً، أرسل الأمر `/unboost`\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    elif result["status"] == "occupied":
        active_user = escape_markdown_v2(result["active_user"])
        await query.edit_message_text(
            f"⏳ *المعالجة المتوازية مستخدمة حالياً*\n\n"
            f"المستخدم {active_user} يستخدمها الآن\\.\n"
            f"سيتم إعلامك فور انتهاء دورهم\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    elif result["status"] == "cooldown":
        remaining = result["expires_in"]
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        await query.edit_message_text(
            f"⏳ *انتهى دورك للتو*\n\n"
            f"يرجى الانتظار {mins} دقيقة و {secs} ثانية قبل أن تتمكن من استخدامها مرة أخرى\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    elif result["status"] == "already_active":
        await query.edit_message_text(
            "ℹ️ أنت تستخدم المعالجة المتوازية حالياً بالفعل\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def unboost_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    container = context.bot_data["container"]
    
    success = await container.concurrency.deactivate_boost(user.id)
    if success:
        await container.concurrency.check_and_notify_waitlist(context.bot)
        await update.message.reply_text(
            "🔴 *تم إيقاف المعالجة المتوازية\\.*\n"
            "يمكنك تفعيلها مرة أخرى بعد دقيقة من الآن\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            "⚠️ *لا تستخدم المعالجة المتوازية حالياً\\.*",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not container.access.is_super_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للسوبر أدمن فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    current_limit = await container.concurrency.get_global_limit()
    await update.message.reply_text(
        f"⚙️ *تحديد الحد الأقصى العام للمعالجة المتوازية*\n\n"
        f"الحد الحالي: `{current_limit}`\n"
        f"اختر الحد الجديد:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=build_setlimit_keyboard(current_limit)
    )

async def handle_setlimit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    
    if not container.access.is_super_admin(query.from_user.id):
        await query.answer("🚫 للسوبر أدمن فقط", show_alert=True)
        return
    
    data = query.data or ""
    value_str = data.replace("adm_act_setlimit_", "")
    if not value_str.isdigit():
        return
    value = int(value_str)
    
    if value < 1 or value > 5:
        await query.answer("⚠️ قيمة غير صالحة.", show_alert=True)
        return
    
    new_limit = await container.concurrency.set_global_limit(value)
    await query.edit_message_text(
        f"⚙️ *تم تحديث الحد الأقصى العام للمعالجة المتوازية*\n"
        f"الحد الجديد: `{new_limit}`",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def set_boost_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not container.access.is_super_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للسوبر أدمن فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    current_limit = await container.concurrency.get_max_boost_limit()
    await update.message.reply_text(
        f"🚀 *تحديد سقف التعزيز المؤقت للمستخدمين*\n\n"
        f"السقف الحالي: `{current_limit}` عمال\n"
        f"اختر السقف الجديد \\(لن يؤثر على الحد العام\\):",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=build_boost_limit_keyboard(current_limit)
    )

async def handle_setboostlimit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    
    if not container.access.is_super_admin(query.from_user.id):
        await query.answer("🚫 للسوبر أدمن فقط", show_alert=True)
        return
    
    data = query.data or ""
    value_str = data.replace("adm_act_setboost_", "")
    if not value_str.isdigit():
        return
    value = int(value_str)
    
    if value < 2 or value > 5:
        await query.answer("⚠️ قيمة غير صالحة.", show_alert=True)
        return
    
    new_limit = await container.concurrency.set_max_boost_limit(value)
    await query.edit_message_text(
        f"🚀 *تم تحديث سقف التعزيز المؤقت*\n"
        f"السقف الجديد: `{new_limit}` عمال متوازيين\n\n"
        f"_لن يؤثر هذا على الحد العام للنظام\\._",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def grant_parallel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not container.access.is_super_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للسوبر أدمن فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "⚠️ *الاستخدام غير صحيح*\nالصيغة: `/grantparallel <ID>`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    user_id = int(args[0])
    await container.concurrency.grant_permanent_access(user_id)

    current_limit = await container.concurrency.get_global_limit()
    if current_limit == 1:
        await update.message.reply_text(
            f"✅ *تم منح الصلاحية*\n"
            f"المستخدم `{escape_markdown_v2(str(user_id))}` يمتلك الآن معالجة متوازية دائمة\\.\n\n"
            f"⚠️ *تنبيه هام:* الحد الأقصى العام الحالي للبوت هو `1`\\. لكي تظهر المعالجة المتوازية للمستخدم، "
            f"يجب عليك رفع الحد باستخدام الأمر `/setlimit 2` أو أكثر\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            f"✅ *تم منح الصلاحية*\n"
            f"المستخدم `{escape_markdown_v2(str(user_id))}` يمتلك الآن معالجة متوازية دائمة\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def revoke_parallel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not container.access.is_super_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للسوبر أدمن فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "⚠️ *الاستخدام غير صحيح*\nالصيغة: `/revokeparallel <ID>`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    user_id = int(args[0])
    await container.concurrency.revoke_access(user_id)
    await update.message.reply_text(
        f"📉 *تم سحب الصلاحية*\n"
        f"تم إلغاء المعالجة المتوازية من المستخدم `{escape_markdown_v2(str(user_id))}`\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )