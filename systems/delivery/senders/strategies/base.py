# File: systems/delivery/senders/strategies/base.py
from __future__ import annotations

from typing import Protocol
from systems.translation_pipeline.base_persona import BasePersona
from systems.translation_pipeline.models.page_job import PageJob


class SessionStrategy(Protocol):
    """Contract for session delivery strategies (Grouped vs Individual)."""
    async def process(self, job: PageJob, handler: BasePersona) -> PageJob: ...
    async def compile_and_send(self, user_id: int, chat_id: int) -> None: ...