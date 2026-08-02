# systems/job_orchestration/queue.py
from __future__ import annotations

import asyncio
from uuid import UUID

from shared.logger import job_logger


class AsyncSingleWorkerQueue:
    """
    An asynchronous FIFO queue implementation.
    Designed to hold only Job IDs (UUIDs) to maintain a stateless architecture.
    """
    def __init__(self, max_size: int = 100) -> None:
        self._queue: asyncio.Queue[UUID] = asyncio.Queue(maxsize=max_size)
        self._max_size = max_size

    async def enqueue(self, job_id: UUID) -> None:
        await self._queue.put(job_id)
        job_logger._logger.info(f"JobID={job_id} | Event=ENQUEUED | QueueSize={self._queue.qsize()}")

    def enqueue_nowait(self, job_id: UUID) -> None:
        self._queue.put_nowait(job_id)
        job_logger._logger.info(f"JobID={job_id} | Event=ENQUEUED | QueueSize={self._queue.qsize()}")

    async def dequeue(self) -> UUID:
        return await self._queue.get()

    async def task_done(self) -> None:
        self._queue.task_done()

    async def size(self) -> int:
        return self._queue.qsize()

    def is_full(self) -> bool:
        return self._queue.full()