# systems/job_orchestration/worker.py
from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Optional, TYPE_CHECKING
from uuid import UUID

from systems.job_orchestration.queue import AsyncSingleWorkerQueue
from systems.job_orchestration.contracts import PipelineProtocol, ErrorNotifierProtocol
from systems.job_orchestration.concurrency.manager import ConcurrencyManager
from shared.logger import job_logger
from systems.translation_pipeline.models.page_job import PageJob, JobState

logger = logging.getLogger(__name__)

class JobSubmissionResult(Enum):
    SUCCESS = 1
    QUEUE_FULL = 2

class JobManager:
    def __init__(
        self, 
        queue_manager: AsyncSingleWorkerQueue, 
        concurrency_manager: ConcurrencyManager, 
        max_running_jobs: int = 1, 
        post_job_delay: int = 0
    ) -> None:
        self._queue = queue_manager
        self._concurrency_manager = concurrency_manager
        self._registry: dict[UUID, PageJob] = {}
        self._lock = asyncio.Lock()
        self._worker_tasks: list[asyncio.Task] = []
        self.max_running_jobs = max_running_jobs
        self.POST_JOB_DELAY_SECONDS = post_job_delay

        self._pipeline: Optional[PipelineProtocol] = None
        self._error_notifier: Optional[ErrorNotifierProtocol] = None

    def attach(self, pipeline: PipelineProtocol, error_notifier: ErrorNotifierProtocol) -> None:
        self._pipeline = pipeline
        self._error_notifier = error_notifier

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
            for i in range(self.max_running_jobs):
                task = asyncio.create_task(self._worker_loop(i + 1))
                self._worker_tasks.append(task)

    async def scale_workers(self, target_count: int) -> None:
        async with self._lock:
            current_count = len(self._worker_tasks)
            if target_count > current_count:
                for i in range(current_count, target_count):
                    task = asyncio.create_task(self._worker_loop(i + 1))
                    self._worker_tasks.append(task)
                logger.info(f"Scaled UP workers: {current_count} -> {target_count}")
            elif target_count < current_count:
                tasks_to_cancel = self._worker_tasks[target_count:]
                self._worker_tasks = self._worker_tasks[:target_count]
                for task in tasks_to_cancel:
                    task.cancel()
                logger.info(f"Scaled DOWN workers: {current_count} -> {target_count}")

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
                    await self._concurrency_manager.acquire_processing_slot(job.user_id)
                    
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
                    # الإلغاء الآمن (Re-enqueue on Cancel)
                    logger.warning(f"Worker {worker_id} cancelled during JobID={current_job_id}. Re-enqueuing...")
                    try:
                        async with self._lock:
                            job.state = JobState.WAITING
                            self._registry[job.job_id] = job
                        self._queue.enqueue_nowait(current_job_id)
                        logger.info(f"JobID={current_job_id} re-enqueued successfully.")
                    except asyncio.QueueFull:
                        logger.error(f"Failed to re-enqueue JobID={current_job_id}: Queue is full! Job is lost.")
                        job.state = JobState.FAILED  # وضع علامة فاشل ليتم حذفه في الـ finally
                    except Exception as e:
                        logger.error(f"Failed to re-enqueue JobID={current_job_id}: {e}. Job is lost.")
                        job.state = JobState.FAILED
                    raise  # إعادة رمي الخطأ لإنهاء الـ Task نهائياً

                except Exception as e:
                    job_logger.log_error(current_job_id, e)
                    await self._transition_state(job, JobState.FAILED)
                    if self._error_notifier:
                        try:
                            await self._error_notifier.notify(job, e)
                        except Exception as notify_err:
                            logger.error(f"Failed to send error notification: {notify_err}")
                
                finally:
                    # يتم تنفيذ هذا الجزء سواء نجحت المهمة، فشلت، أو تم إلغاؤها (بعد إعادة وضعها في الطابور)
                    await self._concurrency_manager.release_processing_slot(job.user_id)
                    await self._queue.task_done()  # إخبار الطابور أننا انتهينا من هذه النسخة
                    
                    # لا نحذف من السجل إلا إذا اكتملت أو فشلت definitively
                    # إذا تم إلغاؤها وأعيد وضعها، لن تكون حالتها FINISHED أو FAILED، لذا تبقى في السجل
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