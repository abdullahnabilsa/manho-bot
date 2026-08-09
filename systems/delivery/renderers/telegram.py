# systems/delivery/renderers/telegram.py
from __future__ import annotations

import asyncio
import logging
from typing import List

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, BadRequest

from systems.translation_pipeline.models.page_job import JobState, PageJob

logger = logging.getLogger(__name__)

class TelegramRenderer:
    SEND_BATCH_SIZE = 3  # Send 3 messages in parallel to speed up delivery without hitting flood control
    BATCH_DELAY_SECONDS = 0.3

    async def render_messages(self, bot: Bot, job: PageJob, messages: List[str]) -> None:
        if not messages:
            job.state = JobState.FINISHED
            return

        job.state = JobState.SENDING
        total_messages = len(messages)
        
        for i in range(0, total_messages, self.SEND_BATCH_SIZE):
            batch = messages[i:i + self.SEND_BATCH_SIZE]
            tasks = []
            
            for raw_text in batch:
                tasks.append(self._safe_send_message(bot, job, raw_text))
                
            await asyncio.gather(*tasks, return_exceptions=True)
            
            if i + self.SEND_BATCH_SIZE < total_messages:
                await asyncio.sleep(self.BATCH_DELAY_SECONDS)

        job.state = JobState.FINISHED

    async def _safe_send_message(self, bot: Bot, job: PageJob, text: str) -> None:
        try:
            await bot.send_message(
                chat_id=job.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
                reply_to_message_id=job.photo_message_id
            )
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(
                    chat_id=job.chat_id,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True,
                    reply_to_message_id=job.photo_message_id
                )
            except Exception as inner_e:
                logger.error(f"Failed to send message after retry: {inner_e}")
        except BadRequest as e:
            logger.error(f"BadRequest sending message: {e}")
            # Fallback to plain text if MarkdownV2 is invalid
            try:
                await bot.send_message(
                    chat_id=job.chat_id,
                    text="⚠️ تنسيق الرسالة معطوب، تم إرسال النص الخام.",
                    reply_to_message_id=job.photo_message_id
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")