# systems/ai_engine/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from uuid import UUID


class BaseAIProvider(ABC):
    """
    Abstract base class for AI providers.
    Enforces strict asynchronous JSON extraction from manga page images.
    """

    @abstractmethod
    async def extract_raw_json(
        self,
        image_bytes: bytes,
        job_id: UUID,
        prompt_text: str,
        api_keys: List[str]
    ) -> Dict[str, Any]:
        """
        Send the image to the AI provider and return strictly parsed JSON.
        
        Raises:
            AIProcessingError: If the provider fails after all fallback attempts.
        """
        pass