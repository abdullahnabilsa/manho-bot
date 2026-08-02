# shared/exceptions.py
from __future__ import annotations

class DomainError(Exception):
    """Base exception for domain-specific errors."""
    pass

class AIProcessingError(DomainError):
    """Raised when the AI Provider fails to process an image."""
    pass

class ValidationFailedError(DomainError):
    """Raised when Pydantic validation fails."""
    pass

class DeliveryError(DomainError):
    """Raised when Telegram delivery fails."""
    pass

class ConcurrencyDeniedError(DomainError):
    """Raised when a user cannot acquire a concurrency slot."""
    pass