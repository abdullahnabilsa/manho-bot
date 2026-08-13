# File: systems/delivery/notifier.py
from __future__ import annotations

import logging
from telegram import Bot
from telegram.constants import ParseMode

from systems.job_orchestration.contracts import ErrorNotifierProtocol
from systems.translation_pipeline.models.page_job import PageJob
from systems.ai_engine.exceptions import ServiceUnavailableError
from systems.delivery.utils import safe_edit_or_send
from utils.markdown_escaper import escape_markdown_v2

logger = logging.getLogger(__name__)

class BotErrorNotifier:
    """Implements ErrorNotifierProtocol to handle job failures gracefully."""
    
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def notify(self, job: PageJob, error: Exception) -> None:
        if isinstance(error, ServiceUnavailableError):
            text = (
                "🚨 *الخدمة تحت الصيانة مؤقتاً\\.*\n"
                "خوادم الذكاء الاصطناعي تواجه ضغطاً شديداً حالياً\\. "
                "يرجى الانتظار دقيقة وإعادة المحاولة\\."
            )
            try:
                await self._bot.send_message(
                    chat_id=job.chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2
                )
                if job.status_message_id:
                    await self._bot.delete_message(
                        chat_id=job.chat_id, message_id=job.status_message_id
                    )
                    job.status_message_id = None
            except Exception as e:
                logger.error(f"Failed to send maintenance notification: {e}")
            return

        text = (
            f"❌ *فشلت المعالجة*\n"
            f"🖼️ الملف: `{escape_markdown_v2(job.file_name)}`\n"
            f"⚠️ لم يتمكن النظام من ترجمة هذه الصفحة\\.\n"
            f"_يرجى المحاولة مرة أخرى لاحقاً\\._"
        )
        try:
            await safe_edit_or_send(self._bot, job, text)
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")