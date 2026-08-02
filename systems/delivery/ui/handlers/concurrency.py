# systems/delivery/ui/handlers/concurrency.py
from __future__ import annotations
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.markdown_escaper import escape_markdown_v2

async def boost_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    container = context.bot_data["container"]
    
    username = f"@{user.username}" if user.username else user.first_name
    result = await container.concurrency.request_boost(user.id, username)
    
    if result["status"] == "granted":
        asyncio.create_task(container.concurrency.auto_expire_boost(user.id, context.bot))
        await update.message.reply_text(
            "🚀 *تم تفعيل التعزيز المؤقت\\!*\n\n"
            "لديك الآن *10 دقائق* لمعالجة صورك بالتوازي \\(حتى 3 صور في نفس الوقت\\)\\. أرسل صورك الآن دفعة واحدة\\!\n\n"
            "لإيقاف التعزيز يدوياً، أرسل الأمر `/unboost`\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    elif result["status"] == "occupied":
        active_user = escape_markdown_v2(result["active_user"])
        await update.message.reply_text(
            f"⏳ *المعالجة المتوازية مستخدمة حالياً*\n\n"
            f"المستخدم {active_user} يستخدمها الآن\\.\n"
            f"سيتم إعلامك فور انتهاء دورهم\\. انتظر دورك\\!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    elif result["status"] == "cooldown":
        mins = int(result["expires_in"] // 60)
        secs = int(result["expires_in"] % 60)
        await update.message.reply_text(
            f"⏳ *انتهى دورك للتو*\n\n"
            f"يرجى الانتظار {mins} دقيقة و {secs} ثانية قبل أن تتمكن من استخدامها مرة أخرى\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    elif result["status"] == "already_active":
        await update.message.reply_text("ℹ️ أنت تستخدم المعالجة المتوازية حالياً بالفعل\\.", parse_mode=ParseMode.MARKDOWN_V2)

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
        await update.message.reply_text("⚠️ *لا تستخدم المعالجة المتوازية حالياً\\.*", parse_mode=ParseMode.MARKDOWN_V2)

async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    # إصلاح: الرد بدلاً من التجاهل الصامت
    if not container.access.is_super_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للسوبر أدمن فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("⚠️ *الاستخدام غير صحيح*\nالصيغة: `/setlimit <1-5>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
        
    limit = int(args[0])
    if limit < 1 or limit > 5:
        await update.message.reply_text("⚠️ *الحد غير صالح*\nيرجى إدخال رقم بين 1 و 5\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    new_limit = await container.concurrency.set_global_limit(limit)
    await update.message.reply_text(f"⚙️ *تم تحديث الحد الأقصى للمعالجة المتوازية*\nالحد الجديد: `{new_limit}`", parse_mode=ParseMode.MARKDOWN_V2)

async def grant_parallel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    # إصلاح: الرد بدلاً من التجاهل الصامت
    if not container.access.is_super_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للسوبر أدمن فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("⚠️ *الاستخدام غير صحيح*\nالصيغة: `/grantparallel <ID>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
        
    user_id = int(args[0])
    await container.concurrency.grant_permanent_access(user_id)

    # إصلاح: تحذير ذكي لمنع سوء الفهم
    current_limit = await container.concurrency.get_global_limit()
    if current_limit == 1:
        await update.message.reply_text(
            f"✅ *تم منح الصلاحية*\nالمستخدم `{escape_markdown_v2(str(user_id))}` يمتلك الآن معالجة متوازية دائمة\\.\n\n"
            f"⚠️ *تنبيه هام:* الحد الأقصى الحالي للبوت هو `1`\\. لكي تظهر المعالجة المتوازية للمستخدم، يجب عليك رفع الحد باستخدام الأمر `/setlimit 2` أو أكثر\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(f"✅ *تم منح الصلاحية*\nالمستخدم `{escape_markdown_v2(str(user_id))}` يمتلك الآن معالجة متوازية دائمة\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def revoke_parallel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    # إصلاح: الرد بدلاً من التجاهل الصامت
    if not container.access.is_super_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للسوبر أدمن فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("⚠️ *الاستخدام غير صحيح*\nالصيغة: `/revokeparallel <ID>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
        
    user_id = int(args[0])
    await container.concurrency.revoke_access(user_id)
    await update.message.reply_text(f"📉 *تم سحب الصلاحية*\nتم إلغاء المعالجة المتوازية من المستخدم `{escape_markdown_v2(str(user_id))}`\\.", parse_mode=ParseMode.MARKDOWN_V2)