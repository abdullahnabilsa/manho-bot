# systems/ai_engine/exceptions.py
from __future__ import annotations

from shared.exceptions import AIProcessingError


class ServiceUnavailableError(AIProcessingError):
    """Raised when the Circuit Breaker is open."""
    pass