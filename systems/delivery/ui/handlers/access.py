# systems/delivery/ui/handlers/access.py
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.markdown_escaper import escape_markdown_v2

async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not await container.access.is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للمشرفين فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("⚠️ *الاستخدام غير صحيح*\nالصيغة الصحيحة: `/adduser <ID>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    user_id = int(args[0])
    escaped_id = escape_markdown_v2(str(user_id))
    added = await container.access.add_user(user_id)
    
    if added:
        await update.message.reply_text(f"✅ *تمت الإضافة بنجاح*\nتم منح المستخدم `{escaped_id}` صلاحية استخدام البوت\\.", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(f"ℹ️ *معلومات*\nالمستخدم `{escaped_id}` موجود مسبقاً في القائمة أو أنه مشرف\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not await container.access.is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للمشرفين فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("⚠️ *الاستخدام غير صحيح*\nالصيغة الصحيحة: `/removeuser <ID>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    user_id = int(args[0])
    escaped_id = escape_markdown_v2(str(user_id))
    removed = await container.access.remove_user(user_id)
    
    if removed:
        await update.message.reply_text(f"🗑️ *تم الحذف بنجاح*\nتم إلغاء صلاحية المستخدم `{escaped_id}`\\.", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(f"⚠️ *غير موجود*\nالمستخدم `{escaped_id}` غير موجود في قائمة المستخدمين\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not container.access.is_super_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للسوبر أدمن فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("⚠️ *الاستخدام غير صحيح*\nالصيغة الصحيحة: `/addadmin <ID>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    user_id = int(args[0])
    escaped_id = escape_markdown_v2(str(user_id))
    added = await container.access.add_admin(user_id)
    
    if added:
        await update.message.reply_text(f"👑 *تمت الترقية بنجاح*\nأصبح المستخدم `{escaped_id}` مشرفاً في البوت\\.", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(f"ℹ️ *معلومات*\nالمستخدم `{escaped_id}` مشرف مسبقاً أو أنه السوبر أدمن\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not container.access.is_super_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للسوبر أدمن فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("⚠️ *الاستخدام غير صحيح*\nالصيغة الصحيحة: `/removeadmin <ID>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    user_id = int(args[0])
    escaped_id = escape_markdown_v2(str(user_id))
    removed = await container.access.remove_admin(user_id)
    
    if removed:
        await update.message.reply_text(f"📉 *تمت الإزالة بنجاح*\nتم سحب صلاحية المشرف من `{escaped_id}`\\.", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(f"⚠️ *غير موجود*\nالمستخدم `{escaped_id}` ليس مشرفاً أو أنه السوبر أدمن \\(لا يمكن حذفه\\)\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not await container.access.is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للمشرفين فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    users = await container.access.get_users()
    admins = await container.access.get_admins()
    super_admin_ids = container.access._super_admin_ids
    join_status = "مفتوح 🟢" if await container.access.is_join_requests_open() else "مغلق 🔴"
    
    text = "📋 *قائمة الصلاحيات*\n\n"
    text += f"🚪 *حالة باب الانضمام:* {join_status}\n\n"
    text += "👑 *المشرفون:*\n"
    for i, adm in enumerate(admins, 1):
        escaped_adm = escape_markdown_v2(adm)
        tag = "السوبر أدمن" if str(adm) in super_admin_ids else "مشرف"
        escaped_tag = escape_markdown_v2(tag)
        text += f"{i}\\. `{escaped_adm}` \\({escaped_tag}\\)\n"
        
    text += "\n👤 *المستخدمون العاديون:*\n"
    if not users:
        text += "_لا يوجد مستخدمون عاديون بعد_\\.\n"
    for i, usr in enumerate(users, 1):
        escaped_usr = escape_markdown_v2(usr)
        text += f"{i}\\. `{escaped_usr}`\n"
        
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

async def open_requests_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not await container.access.is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للمشرفين فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    await container.access.set_join_requests(True)
    await update.message.reply_text("🟢 *تم فتح باب الانضمام\\.*\nأي مستخدم جديد يضغط /start سيتم إرسال طلبه إليك\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def close_requests_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    container = context.bot_data["container"]
    if not await container.access.is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذا الأمر مخصص للمشرفين فقط\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    await container.access.set_join_requests(False)
    await update.message.reply_text("🔴 *تم إغلاق باب الانضمام\\.*\nلن يستلم البوت أي طلبات جديدة، وسيتم تجاهل المستخدمين الجدد بصمت لتوفير الموارد\\.", parse_mode=ParseMode.MARKDOWN_V2)

async def handle_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    container = context.bot_data["container"]
    
    data = query.data
    action, user_id_str = data.split(":")
    user_id = int(user_id_str)
    
    admin_name = escape_markdown_v2(query.from_user.first_name or "مشرف")
    if query.from_user.username:
        admin_mention = f"@{escape_markdown_v2(query.from_user.username)}"
    else:
        admin_mention = f"[{admin_name}](tg://user?id={query.from_user.id})"

    escaped_user_id = escape_markdown_v2(user_id_str)
    
    pending_requests = await container.access.get_pending_requests(user_id)
    if not pending_requests:
        await query.answer("تمت معالجة هذا الطلب مسبقاً.", show_alert=True)
        try:
            await query.edit_message_text(f"ℹ️ *تمت معالجة هذا الطلب مسبقاً\\.*\nالمستخدم `{escaped_user_id}` تمت إضافته أو رفضه\\.", parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass
        return

    user_display = f"`{escaped_user_id}`"
    try:
        user_chat = await context.bot.get_chat(user_id)
        if user_chat.username:
            user_display = f"@{escape_markdown_v2(user_chat.username)} \\(`{escaped_user_id}`\\)"
        else:
            escaped_first_name = escape_markdown_v2(user_chat.first_name or "N/A")
            user_display = f"{escaped_first_name} \\(`{escaped_user_id}`\\)"
    except Exception:
        pass

    if action == "accept_req":
        if await container.access.is_authorized(user_id):
            await query.answer("هذا المستخدم موجود بالفعل في البوت.", show_alert=True)
            await container.access.clear_requests(user_id)
            return
            
        await container.access.add_user(user_id)
        
        new_text = (
            f"✅ *تم قبول الطلب\\!*\n\n"
            f"👤 *المستخدم:* {user_display}\n"
            f"👑 *بواسطة المشرف:* {admin_mention}"
        )
        
        for adm_id, msg_id in pending_requests:
            try:
                await context.bot.edit_message_text(chat_id=adm_id, message_id=msg_id, text=new_text, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception:
                pass
                
        await container.access.clear_requests(user_id)
        try:
            user_msg = (
                f"🎉 *مبروك\\! تم قبول طلب انضمامك\\.*\n\n"
                f"👑 تمت الموافقة عليك بواسطة المشرف: {admin_mention}\n\n"
                f"يمكنك الآن استخدام البوت بحرية\\.\n"
                f"أرسل /start للبدء\\."
            )
            await context.bot.send_message(chat_id=user_id, text=user_msg, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass

    elif action == "reject_req":
        new_text = (
            f"❌ *تم رفض الطلب\\.*\n\n"
            f"👤 *المستخدم:* {user_display}\n"
            f"👑 *بواسطة المشرف:* {admin_mention}"
        )
        
        for adm_id, msg_id in pending_requests:
            try:
                await context.bot.edit_message_text(chat_id=adm_id, message_id=msg_id, text=new_text, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception:
                pass
                
        await container.access.clear_requests(user_id)
        
        try:
            user_msg = (
                f"🚫 *تم رفض طلب الانضمام\\.*\n\n"
                f"للأسف، تم رفض طلب انضمامك من قبل إدارة البوت\\."
            )
            await context.bot.send_message(chat_id=user_id, text=user_msg, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass