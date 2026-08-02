# shared/logger.py
from __future__ import annotations

import logging
import sys
import time
from typing import Optional
from uuid import UUID


class JobMetricsLogger:
    """
    Dedicated logger for tracking Job lifecycle metrics.
    """
    def __init__(self, name: str = "manga_bot") -> None:
        self._logger = logging.getLogger(name)
        self._configure_logger()
        self._start_times: dict[UUID, float] = {}
        self._receive_times: dict[UUID, float] = {}

    def _configure_logger(self) -> None:
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)

    def log_received(self, job_id: UUID, user_id: int) -> None:
        recv_time = time.time()
        self._receive_times[job_id] = recv_time
        self._logger.info(f"JobID={job_id} | Event=RECEIVED | UserID={user_id} | ReceiveTime={recv_time:.3f}")

    def log_started(self, job_id: UUID) -> None:
        start_time = time.time()
        self._start_times[job_id] = start_time
        recv_time = self._receive_times.get(job_id, start_time)
        queue_wait = start_time - recv_time
        self._logger.info(f"JobID={job_id} | Event=STARTED | StartTime={start_time:.3f} | QueueWait={queue_wait:.3f}s")

    def log_completed(self, job_id: UUID, scene_count: int, element_count: int) -> None:
        end_time = time.time()
        start_time = self._start_times.get(job_id, end_time)
        duration = end_time - start_time
        self._logger.info(
            f"JobID={job_id} | Event=COMPLETED | EndTime={end_time:.3f} | Duration={duration:.3f}s | "
            f"Scenes={scene_count} | Elements={element_count}"
        )
        self._cleanup(job_id)

    def log_error(self, job_id: UUID, error: Exception) -> None:
        end_time = time.time()
        start_time = self._start_times.get(job_id, end_time)
        duration = end_time - start_time
        self._logger.error(
            f"JobID={job_id} | Event=FAILED | EndTime={end_time:.3f} | Duration={duration:.3f}s | "
            f"ErrorType={type(error).__name__} | Detail={str(error)}",
            exc_info=True
        )
        self._cleanup(job_id)

    def _cleanup(self, job_id: UUID) -> None:
        self._start_times.pop(job_id, None)
        self._receive_times.pop(job_id, None)

job_logger = JobMetricsLogger()