# systems/job_orchestration/contracts.py
from __future__ import annotations

from typing import Protocol, Awaitable
from systems.translation_pipeline.models.page_job import PageJob


class PipelineProtocol(Protocol):
    """Contract for the Delivery Pipeline to process jobs."""
    async def process(self, job: PageJob) -> PageJob: ...
    async def render(self, job: PageJob) -> PageJob: ...
    async def send(self, job: PageJob) -> PageJob: ...


class ErrorNotifierProtocol(Protocol):
    """Contract for the Error Notifier to handle job failures."""
    async def notify(self, job: PageJob, error: Exception) -> None: ...