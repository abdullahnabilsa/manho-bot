# File: main.py
from __future__ import annotations

import asyncio
import logging
from telegram import Update, BotCommand, BotCommandScopeChat
from telegram.ext import (
    Application, ApplicationBuilder, ContextTypes, MessageHandler, 
    filters, CommandHandler, CallbackQueryHandler, TypeHandler
)
from telegram.constants import ParseMode

from config.settings import Settings
from shared.database import Database
from shared.event_bus import EventBus
from shared.logger import job_logger
from shared.container import ServiceContainer
from utils.image_optimizer import optimize_image

from systems.access_control.manager import AccessManager
from systems.access_control.api_key_manager import APIKeyManager
from systems.access_control.user_settings import UserSettingsManager
from systems.access_control.middleware import firewall_middleware

from systems.ai_engine.gemini import GeminiProvider

from systems.translation_pipeline.registry import PersonaRegistry

from systems.job_orchestration.queue import AsyncSingleWorkerQueue
from systems.job_orchestration.worker import JobManager

from systems.delivery.batch import BatchManager
from systems.delivery.renderers.telegram import TelegramRenderer
from systems.delivery.senders.strategies.grouped_session import GroupedSessionStrategy
from systems.delivery.senders.strategies.individual_session import IndividualSessionStrategy
from systems.delivery.notifier import BotErrorNotifier
from systems.delivery.pipeline import DeliveryPipeline

from systems.glossary.manager import GlossaryManager

# UI Handlers
from systems.delivery.ui.handlers.start import start_command, help_command
from systems.delivery.ui.handlers.settings import settings_command, settings_callback
from systems.delivery.ui.handlers.session import start_session_command, end_session_command, cancel_command, receive_session_filename
from systems.delivery.ui.handlers.admin import (
    add_public_key_command, list_public_keys_command, remove_public_key_command,
    upload_dict_command, download_dict_command,
    handle_apikey_callback, handle_admin_cancel
)
from systems.delivery.ui.handlers.access import (
    add_user_command, remove_user_command, add_admin_command, remove_admin_command, 
    list_users_command, open_requests_command, close_requests_command,
    handle_request_callback, handle_access_callback
)
from systems.delivery.ui.handlers.messages import handle_image, handle_text, handle_document
from systems.delivery.ui.middlewares import state_purge_middleware, session_guard_middleware

settings = Settings()
logging.basicConfig(
    level=settings.log_level.upper(), 
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", 
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("manga_bot.main")

async def post_init(app: Application) -> None:
    bot = app.bot
    
    db = Database(db_path="manga_bot.db")
    await db.connect()
    event_bus = EventBus()
    
    access_manager = AccessManager(db=db, super_admin_ids=settings.super_admin_ids)
    api_key_manager = APIKeyManager(db=db)
    settings_manager = UserSettingsManager(db=db)
    
    ai_provider = GeminiProvider(
        timeout=settings.ai_timeout_seconds, 
        cb_threshold=settings.cb_failure_threshold, 
        cb_cooldown=settings.cb_cooldown_seconds
    )
    
    persona_registry = PersonaRegistry(plugins_dir="systems/translation_pipeline/plugins")
    
    queue_manager = AsyncSingleWorkerQueue(max_size=settings.queue_max_size)
    
    job_manager = JobManager(
        queue_manager=queue_manager, 
        post_job_delay=settings.post_job_delay_seconds
    )
    
    batch_manager = BatchManager()
    telegram_renderer = TelegramRenderer()
    
    grouped_strategy = GroupedSessionStrategy(
        bot=bot, batch=batch_manager, settings=settings_manager,
        personas=persona_registry, queue=queue_manager, renderer=telegram_renderer
    )
    
    individual_strategy = IndividualSessionStrategy(
        bot=bot, batch=batch_manager, settings=settings_manager,
        personas=persona_registry, queue=queue_manager, renderer=telegram_renderer
    )
    
    error_notifier = BotErrorNotifier(bot=bot)
    glossary_manager = GlossaryManager()
    
    delivery_pipeline = DeliveryPipeline(
        bot=bot,
        ai_provider=ai_provider,
        persona_registry=persona_registry,
        api_key_manager=api_key_manager,
        settings_manager=settings_manager,
        batch_manager=batch_manager,
        grouped_strategy=grouped_strategy,
        individual_strategy=individual_strategy,
        image_optimizer=optimize_image,
        queue_manager=queue_manager,
        glossary_manager=glossary_manager
    )
    
    job_manager.attach(
        pipeline=delivery_pipeline,
        error_notifier=error_notifier
    )
    
    container = ServiceContainer(
        db=db, bot=bot, event_bus=event_bus,
        access=access_manager, api_keys=api_key_manager, settings=settings_manager,
        ai=ai_provider, personas=persona_registry,
        queue=queue_manager, jobs=job_manager,
        batch=batch_manager, renderer=telegram_renderer,
        delivery=delivery_pipeline, notifier=error_notifier,
        glossary=glossary_manager
    )
    app.bot_data["container"] = container
    
    public_commands = [
        BotCommand("start", "بدء استخدام البوت"), BotCommand("settings", "فتح الإعدادات"),
        BotCommand("help", "دليل الاستخدام"), BotCommand("start_session", "بدء الجلسة"),
        BotCommand("end_session", "إنهاء الجلسة"), BotCommand("cancel", "إلغاء الجلسة")
    ]
    await bot.set_my_commands(public_commands)
    
    admin_commands = public_commands + [
        BotCommand("addkey", "➕ إضافة مفتاح API"), BotCommand("listkeys", "📋 عرض مفاتيح API"),
        BotCommand("removekey", "🗑️ حذف مفتاح API"), BotCommand("adduser", "➕ إضافة مستخدم"),
        BotCommand("removeuser", "🗑️ حذف مستخدم"), BotCommand("listusers", "📋 عرض المستخدمين"),
        BotCommand("openrequests", "🟢 فتح باب الانضمام"), BotCommand("closerequests", "🔴 إغلاق باب الانضمام"),
        BotCommand("uploaddict", "📚 رفع قاموس المصطلحات"), BotCommand("downloaddict", "📥 تحميل القاموس"),
    ]
    super_admin_commands = admin_commands + [
        BotCommand("addadmin", "👑 ترقية لمشرف"), BotCommand("removeadmin", "📉 إزالة مشرف")
    ]
    
    admins = await access_manager.get_admins()
    for admin_id in admins:
        try:
            cmds = super_admin_commands if access_manager.is_super_admin(int(admin_id)) else admin_commands
            await bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=int(admin_id)))
        except Exception as e:
            logger.warning(f"Could not set admin commands for {admin_id}: {e}")
            
    await job_manager.start()

async def post_shutdown(app: Application) -> None:
    container: ServiceContainer = app.bot_data.get("container")
    if container:
        await container.jobs.stop()
        await container.db.close()

def main() -> None:
    app = ApplicationBuilder().token(settings.telegram_bot_token).post_init(post_init).post_shutdown(post_shutdown).build()

    # Middleware stack (ordered by priority)
    app.add_handler(TypeHandler(Update, firewall_middleware), group=-3)
    app.add_handler(TypeHandler(Update, state_purge_middleware), group=-2)
    app.add_handler(TypeHandler(Update, session_guard_middleware), group=-1)
    
    # Public commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("start_session", start_session_command))
    app.add_handler(CommandHandler("end_session", end_session_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    
    # Admin commands
    app.add_handler(CommandHandler("addkey", add_public_key_command))
    app.add_handler(CommandHandler("listkeys", list_public_keys_command))
    app.add_handler(CommandHandler("removekey", remove_public_key_command))
    app.add_handler(CommandHandler("uploaddict", upload_dict_command))
    app.add_handler(CommandHandler("downloaddict", download_dict_command))
    
    # Access management commands
    app.add_handler(CommandHandler("adduser", add_user_command))
    app.add_handler(CommandHandler("removeuser", remove_user_command))
    app.add_handler(CommandHandler("listusers", list_users_command))
    app.add_handler(CommandHandler("openrequests", open_requests_command))
    app.add_handler(CommandHandler("closerequests", close_requests_command))
    
    # Super admin commands
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("removeadmin", remove_admin_command))
    
    # Persistent keyboard buttons
    app.add_handler(MessageHandler(filters.Regex("⚙️ الإعدادات"), settings_command))
    app.add_handler(MessageHandler(filters.Regex("📖 المساعدة"), help_command))
    app.add_handler(MessageHandler(filters.Regex("🟢 بدء الجلسة"), start_session_command))
    app.add_handler(MessageHandler(filters.Regex("🔴 إنهاء الجلسة"), end_session_command))
    
    # Callback query handlers (ordered by specificity)
    # Settings callbacks
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^(open_|set_|back_|toggle_|add_|del_)"))
    
    # Interactive access management callbacks
    app.add_handler(CallbackQueryHandler(handle_access_callback, pattern="^adm_(sel|conf|nav)_access_"))
    
    # Interactive API key management callbacks
    app.add_handler(CallbackQueryHandler(handle_apikey_callback, pattern="^adm_(sel|conf|nav)_apikey_"))
    
    # Admin cancel (dismiss interactive panel)
    app.add_handler(CallbackQueryHandler(handle_admin_cancel, pattern="^adm_cancel$"))
    
    # Join request callbacks
    app.add_handler(CallbackQueryHandler(handle_request_callback, pattern="^(accept_req|reject_req)"))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.Document.TEXT, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))

    logger.info("Starting Manga Translation Bot with Sequential Processing Engine...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()