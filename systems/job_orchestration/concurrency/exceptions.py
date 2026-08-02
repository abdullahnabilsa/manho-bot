# systems/job_orchestration/concurrency/exceptions.py
from __future__ import annotations

class ConcurrencyError(Exception):
    pass

class LeaseExpiredError(ConcurrencyError):
    pass

class ConcurrencyLimitReached(ConcurrencyError):
    pass