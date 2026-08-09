# systems/job_orchestration/worker.py
from __future__ import annotations

import asyncio
import heapq
import logging
import time
from enum import Enum
from typing import Optional, Tuple, List, TYPE_CHECKING
from uuid import UUID

from systems.job_orchestration.queue import AsyncSingleWorkerQueue
from systems.job_orchestration.contracts import PipelineProtocol, ErrorNotifierProtocol
from shared.logger import job_logger
from systems.translation_pipeline.models.page_job import PageJob, JobState

logger = logging.getLogger(__name__)

class JobSubmissionResult(Enum):
    SUCCESS = 1
    QUEUE_FULL = 2

class JobManager:
    STATIC_AI_WORKERS: int = 4
    STATIC_DELIVERY_WORKERS: int = 2  # Increased to prevent UI blocking during DOCX generation

    def __init__(
        self, 
        ai_queue: AsyncSingleWorkerQueue,
        delivery_queue: AsyncSingleWorkerQueue,
        post_job_delay: int = 0
    ) -> None:
        self._ai_queue = ai_queue
        self._delivery_queue = delivery_queue
        self._registry: dict[UUID, PageJob] = {}
        self._lock = asyncio.Lock()
        self._worker_tasks: list[asyncio.Task] = []
        self.POST_JOB_DELAY_SECONDS = post_job_delay

        self._pipeline: Optional[PipelineProtocol] = None
        self._error_notifier: Optional[ErrorNotifierProtocol] = None
        
        self._active_user_id: Optional[int] = None
        self._waiting_queue: List[Tuple[int, float, int, int]] = []

    def attach(self, pipeline: PipelineProtocol, error_notifier: ErrorNotifierProtocol) -> None:
        self._pipeline = pipeline
        self._error_notifier = error_notifier

    async def request_processing(self, user_id: int, chat_id: int, image_count: int) -> bool:
        async with self._lock:
            if self._active_user_id is None:
                self._active_user_id = user_id
                return True
            if self._active_user_id == user_id:
                return True
            
            for item in self._waiting_queue:
                if item[2] == user_id:
                    return False
                    
            heapq.heappush(self._waiting_queue, (image_count, time.time(), user_id, chat_id))
            return False

    async def release_active_user(self) -> Optional[Tuple[int, int]]:
        async with self._lock:
            self._active_user_id = None
            if self._waiting_queue:
                _, _, next_user_id, next_chat_id = heapq.heappop(self._waiting_queue)
                self._active_user_id = next_user_id
                return next_user_id, next_chat_id
            return None

    async def is_active_user(self, user_id: int) -> bool:
        async with self._lock:
            return self._active_user_id == user_id

    async def get_active_user(self) -> Optional[int]:
        async with self._lock:
            return self._active_user_id

    async def cancel_waiting_user(self, user_id: int) -> None:
        async with self._lock:
            self._waiting_queue = [item for item in self._waiting_queue if item[2] != user_id]
            heapq.heapify(self._waiting_queue)

    async def submit_job(self, job: PageJob) -> JobSubmissionResult:
        async with self._lock:
            if self._ai_queue.is_full():
                return JobSubmissionResult.QUEUE_FULL
            self._registry[job.job_id] = job
        
        job_logger.log_received(job.job_id, job.user_id)
        
        try:
            self._ai_queue.enqueue_nowait(job.job_id)
        except asyncio.QueueFull:
            async with self._lock:
                del self._registry[job.job_id]
            return JobSubmissionResult.QUEUE_FULL

        return JobSubmissionResult.SUCCESS

    async def get_job(self, job_id: UUID) -> Optional[PageJob]:
        async with self._lock:
            return self._registry.get(job_id)

    async def get_ai_queue_size(self) -> int:
        return await self._ai_queue.size()

    async def get_delivery_queue_size(self) -> int:
        return await self._delivery_queue.size()

    async def start(self) -> None:
        if not self._worker_tasks:
            for i in range(self.STATIC_AI_WORKERS):
                task = asyncio.create_task(self._ai_worker_loop(i + 1))
                self._worker_tasks.append(task)
            for i in range(self.STATIC_DELIVERY_WORKERS):
                task = asyncio.create_task(self._delivery_worker_loop(i + 1))
                self._worker_tasks.append(task)
            logger.info(f"Worker Pool initialized: {self.STATIC_AI_WORKERS} AI, {self.STATIC_DELIVERY_WORKERS} Delivery.")

    async def stop(self) -> None:
        for task in self._worker_tasks:
            task.cancel()
        for task in self._worker_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._worker_tasks.clear()

    async def _ai_worker_loop(self, worker_id: int) -> None:
        try:
            while True:
                current_job_id = await self._ai_queue.dequeue()
                job = await self.get_job(current_job_id)

                if not job or not self._pipeline:
                    job_logger.log_error(current_job_id, RuntimeError("Job missing or pipeline not attached"))
                    await self._ai_queue.task_done()
                    continue

                job_logger.log_started(current_job_id)
                
                try:
                    await self._transition_state(job, JobState.PROCESSING)
                    job = await self._pipeline.process(job)

                    await self._transition_state(job, JobState.RENDERING)
                    job = await self._pipeline.render(job)

                    await self._delivery_queue.enqueue(job.job_id)

                except asyncio.CancelledError:
                    logger.warning(f"AI Worker {worker_id} cancelled during JobID={current_job_id}. Re-enqueuing...")
                    try:
                        async with self._lock:
                            job.state = JobState.WAITING
                            self._registry[job.job_id] = job
                        self._ai_queue.enqueue_nowait(current_job_id)
                    except asyncio.QueueFull:
                        logger.error(f"Failed to re-enqueue JobID={current_job_id}: Queue is full!")
                        job.state = JobState.FAILED
                    raise

                except Exception as e:
                    error_str = str(e)
                    if "Processing requires an active session" in error_str:
                        logger.info(f"JobID={current_job_id} silently dropped due to session cancellation.")
                        async with self._lock:
                            self._registry.pop(job.job_id, None)
                    else:
                        job_logger.log_error(current_job_id, e)
                        await self._transition_state(job, JobState.FAILED)
                        job.error = str(e)
                        await self._delivery_queue.enqueue(job.job_id)
                
                finally:
                    await self._ai_queue.task_done()
                    
        except asyncio.CancelledError:
            logger.info(f"AI Worker {worker_id} gracefully shut down.")
            return

    async def _delivery_worker_loop(self, worker_id: int) -> None:
        try:
            while True:
                current_job_id = await self._delivery_queue.dequeue()
                job = await self.get_job(current_job_id)

                if not job or not self._pipeline:
                    await self._delivery_queue.task_done()
                    continue

                try:
                    if job.state == JobState.FAILED or job.error:
                        if self._error_notifier:
                            try:
                                await self._error_notifier.notify(job, RuntimeError(job.error or "Unknown AI Error"))
                            except Exception as notify_err:
                                logger.error(f"Failed to send error notification: {notify_err}")
                    else:
                        await self._transition_state(job, JobState.SENDING)
                        job = await self._pipeline.deliver(job)
                        await self._transition_state(job, JobState.FINISHED)
                        job_logger.log_completed(current_job_id, 0, 0)

                except Exception as e:
                    logger.error(f"Delivery failed for JobID={current_job_id}: {e}", exc_info=True)
                    await self._transition_state(job, JobState.FAILED)
                
                finally:
                    await self._delivery_queue.task_done()
                    if job.state in [JobState.FINISHED, JobState.FAILED]:
                        async with self._lock:
                            self._registry.pop(job.job_id, None)
                    
                    await asyncio.sleep(self.POST_JOB_DELAY_SECONDS)
                    
        except asyncio.CancelledError:
            logger.info(f"Delivery Worker {worker_id} gracefully shut down.")
            return

    async def _transition_state(self, job: PageJob, new_state: JobState) -> None:
        async with self._lock:
            job.state = new_state
            self._registry[job.job_id] = job