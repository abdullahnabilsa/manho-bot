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
    STATIC_WORKERS_COUNT: int = 5

    def __init__(
        self, 
        queue_manager: AsyncSingleWorkerQueue, 
        post_job_delay: int = 0
    ) -> None:
        self._queue = queue_manager
        self._registry: dict[UUID, PageJob] = {}
        self._lock = asyncio.Lock()
        self._worker_tasks: list[asyncio.Task] = []
        self.POST_JOB_DELAY_SECONDS = post_job_delay

        self._pipeline: Optional[PipelineProtocol] = None
        self._error_notifier: Optional[ErrorNotifierProtocol] = None
        
        # Phase 1: Gatekeeper State
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
            if self._queue.is_full():
                return JobSubmissionResult.QUEUE_FULL
            self._registry[job.job_id] = job
        
        job_logger.log_received(job.job_id, job.user_id)
        
        try:
            self._queue.enqueue_nowait(job.job_id)
        except asyncio.QueueFull:
            async with self._lock:
                del self._registry[job.job_id]
            return JobSubmissionResult.QUEUE_FULL

        return JobSubmissionResult.SUCCESS

    async def get_job(self, job_id: UUID) -> Optional[PageJob]:
        async with self._lock:
            return self._registry.get(job_id)

    async def start(self) -> None:
        if not self._worker_tasks:
            for i in range(self.STATIC_WORKERS_COUNT):
                task = asyncio.create_task(self._worker_loop(i + 1))
                self._worker_tasks.append(task)
            logger.info(f"Static Worker Pool initialized with {self.STATIC_WORKERS_COUNT} workers.")

    async def stop(self) -> None:
        for task in self._worker_tasks:
            task.cancel()
        for task in self._worker_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._worker_tasks.clear()

    async def _worker_loop(self, worker_id: int) -> None:
        try:
            while True:
                current_job_id = await self._queue.dequeue()
                job = await self.get_job(current_job_id)

                if not job or not self._pipeline:
                    job_logger.log_error(current_job_id, RuntimeError("Job missing or pipeline not attached"))
                    await self._queue.task_done()
                    continue

                job_logger.log_started(current_job_id)
                job_completed_successfully = False
                
                try:
                    await self._transition_state(job, JobState.PROCESSING)
                    job = await self._pipeline.process(job)

                    await self._transition_state(job, JobState.RENDERING)
                    job = await self._pipeline.render(job)

                    await self._transition_state(job, JobState.SENDING)
                    job = await self._pipeline.send(job)

                    await self._transition_state(job, JobState.FINISHED)
                    
                    scene_count = len(job.page_data.scenes) if job.page_data else 0
                    element_count = sum(len(s.elements) for s in job.page_data.scenes) if job.page_data else 0
                    job_logger.log_completed(current_job_id, scene_count, element_count)
                    job_completed_successfully = True

                except asyncio.CancelledError:
                    logger.warning(f"Worker {worker_id} cancelled during JobID={current_job_id}. Re-enqueuing...")
                    try:
                        async with self._lock:
                            job.state = JobState.WAITING
                            self._registry[job.job_id] = job
                        self._queue.enqueue_nowait(current_job_id)
                        logger.info(f"JobID={current_job_id} re-enqueued successfully.")
                    except asyncio.QueueFull:
                        logger.error(f"Failed to re-enqueue JobID={current_job_id}: Queue is full! Job is lost.")
                        job.state = JobState.FAILED
                    except Exception as e:
                        logger.error(f"Failed to re-enqueue JobID={current_job_id}: {e}. Job is lost.")
                        job.state = JobState.FAILED
                    raise

                except Exception as e:
                    error_str = str(e)
                    if "Processing requires an active session" in error_str:
                        logger.info(f"JobID={current_job_id} silently dropped due to session cancellation.")
                    else:
                        job_logger.log_error(current_job_id, e)
                        await self._transition_state(job, JobState.FAILED)
                        if self._error_notifier:
                            try:
                                await self._error_notifier.notify(job, e)
                            except Exception as notify_err:
                                logger.error(f"Failed to send error notification: {notify_err}")
                
                finally:
                    await self._queue.task_done()
                    
                    if job_completed_successfully or job.state == JobState.FAILED:
                        async with self._lock:
                            self._registry.pop(job.job_id, None)
                    
                    await asyncio.sleep(self.POST_JOB_DELAY_SECONDS)
                    
        except asyncio.CancelledError:
            logger.info(f"Worker {worker_id} gracefully shut down.")
            return

    async def _transition_state(self, job: PageJob, new_state: JobState) -> None:
        async with self._lock:
            job.state = new_state
            self._registry[job.job_id] = job