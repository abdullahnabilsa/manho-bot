# systems/delivery/renderers/telegram.py
from __future__ import annotations

import asyncio
import logging
from typing import List

from telegram import Bot
from telegram.constants import ParseMode

from systems.translation_pipeline.models.page_job import JobState, PageJob

logger = logging.getLogger(__name__)

class TelegramRenderer:
    SEND_DELAY_SECONDS = 0.3

    async def render_messages(self, bot: Bot, job: PageJob, messages: List[str]) -> None:
        if not messages:
            job.state = JobState.FINISHED
            return

        job.state = JobState.SENDING
        total_messages = len(messages)
        
        for i, raw_text in enumerate(messages, start=1):
            try:
                await bot.send_message(
                    chat_id=job.chat_id,
                    text=raw_text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True
                )
                if i < total_messages:
                    await asyncio.sleep(self.SEND_DELAY_SECONDS)
            except Exception as e:
                logger.error(f"JobID={job.job_id} | Failed to send message {i}/{total_messages}: {str(e)}", exc_info=True)
                if i < total_messages:
                    await asyncio.sleep(self.SEND_DELAY_SECONDS)

        job.state = JobState.FINISHED