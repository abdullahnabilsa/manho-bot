# systems/delivery/senders/base.py
from __future__ import annotations

from typing import Protocol
from systems.translation_pipeline.base_persona import BasePersona
from systems.translation_pipeline.models.page_job import PageJob


class SenderProtocol(Protocol):
    async def process(self, job: PageJob, handler: BasePersona) -> PageJob: ...