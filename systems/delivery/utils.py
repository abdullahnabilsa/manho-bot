# systems/delivery/utils.py
from __future__ import annotations

import asyncio
import logging
from telegram.constants import ParseMode
from telegram.error import RetryAfter, BadRequest

from systems.translation_pipeline.models.page_job import PageJob

logger = logging.getLogger(__name__)

async def safe_edit_or_send(bot, job: PageJob, text: str) -> None:
    try:
        if job.status_message_id:
            await bot.edit_message_text(
                chat_id=job.chat_id, message_id=job.status_message_id,
                text=text, parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            raise BadRequest("No status message ID")
    except (RetryAfter, BadRequest, Exception) as e:
        if isinstance(e, RetryAfter):
            await asyncio.sleep(e.retry_after)
        try:
            msg = await bot.send_message(chat_id=job.chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
            job.status_message_id = msg.message_id
        except Exception:
            pass

async def safe_delete_message(bot, job: PageJob) -> None:
    if not job.status_message_id:
        return
    try:
        await bot.delete_message(chat_id=job.chat_id, message_id=job.status_message_id)
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await bot.delete_message(chat_id=job.chat_id, message_id=job.status_message_id)
        except Exception:
            pass
    except Exception:
        pass