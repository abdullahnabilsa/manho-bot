# systems/ai_engine/gemini.py
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

import aiohttp

from systems.ai_engine.base import BaseAIProvider
from systems.ai_engine.exceptions import ServiceUnavailableError, AIProcessingError

logger = logging.getLogger(__name__)

class GeminiProvider(BaseAIProvider):
    """
    Concrete AI provider for Google Gemini API.
    Implements multi-key, multi-model fallback and a Circuit Breaker.
    """

    FALLBACK_MODELS: List[str] = [
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]

    MAX_RETRIES_PER_MODEL = 2
    RETRY_DELAY_SECONDS = 1.0

    def __init__(self, timeout: float = 60.0, cb_threshold: int = 5, cb_cooldown: int = 60) -> None:
        self._base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        
        self._cb_threshold = cb_threshold
        self._cb_cooldown = cb_cooldown
        self._cb_failures = 0
        self._cb_open_until = 0.0
        self._cb_lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _check_circuit(self) -> None:
        async with self._cb_lock:
            if self._cb_failures >= self._cb_threshold and time.time() < self._cb_open_until:
                raise ServiceUnavailableError("Circuit Breaker is OPEN. AI Service is temporarily unavailable.")

    async def _record_success(self) -> None:
        async with self._cb_lock:
            if self._cb_failures > 0:
                logger.info("Circuit Breaker CLOSED. Service restored.")
            self._cb_failures = 0
            self._cb_open_until = 0.0

    async def _record_failure(self) -> None:
        async with self._cb_lock:
            self._cb_failures += 1
            if self._cb_failures >= self._cb_threshold:
                self._cb_open_until = time.time() + self._cb_cooldown
                logger.warning(f"Circuit Breaker OPENED for {self._cb_cooldown}s due to {self._cb_failures} consecutive failures.")

    async def extract_raw_json(
        self,
        image_bytes: bytes,
        job_id: UUID,
        prompt_text: str,
        api_keys: List[str]
    ) -> Dict[str, Any]:
        await self._check_circuit()

        if not api_keys:
            await self._record_failure()
            raise AIProcessingError(f"JobID={job_id} | No API keys provided.")

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        payload = self._build_payload(b64_image, prompt_text)

        last_exception: Optional[Exception] = None
        session = await self._get_session()

        for key_idx, api_key in enumerate(api_keys):
            key_masked = api_key[:8] + "..." + api_key[-4:]
            for model_name in self.FALLBACK_MODELS:
                for attempt in range(1, self.MAX_RETRIES_PER_MODEL + 1):
                    try:
                        logger.info(f"JobID={job_id} | Key {key_idx+1}/{len(api_keys)} ({key_masked}) | Model: {model_name} | Attempt {attempt}")
                        result = await self._call_model(session, model_name, payload, job_id, api_key)
                        
                        await self._record_success()
                        logger.info(f"JobID={job_id} | Success with key {key_masked} and model: {model_name}")
                        return result
                    
                    except (asyncio.TimeoutError, RuntimeError) as e:
                        error_str = str(e)
                        is_transient = isinstance(e, asyncio.TimeoutError) or "503" in error_str or "429" in error_str
                        
                        if is_transient and attempt < self.MAX_RETRIES_PER_MODEL:
                            logger.warning(f"JobID={job_id} | Transient error on {model_name}. Retrying in {self.RETRY_DELAY_SECONDS}s...")
                            await asyncio.sleep(self.RETRY_DELAY_SECONDS)
                            continue
                        else:
                            logger.warning(f"JobID={job_id} | Model {model_name} failed for key {key_masked}: {error_str}")
                            last_exception = e
                            break 
                            
                    except Exception as e:
                        logger.warning(f"JobID={job_id} | Unexpected error on {model_name} for key {key_masked}: {str(e)}")
                        last_exception = e
                        break 

        await self._record_failure()
        raise AIProcessingError(
            f"All API keys and Gemini models failed for JobID={job_id}. Last error: {str(last_exception)}"
        )

    def _build_payload(self, b64_image: str, prompt_text: str) -> Dict[str, Any]:
        return {
            "contents": [
                {
                    "parts": [
                        {"text": "Extract all text elements in Arabic reading order (Top-to-Bottom, Right-to-Left)."},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image,
                            }
                        }
                    ]
                }
            ],
            "system_instruction": {
                "parts": [
                    {"text": prompt_text}
                ]
            },
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        }

    async def _call_model(
        self,
        session: aiohttp.ClientSession,
        model_name: str,
        payload: Dict[str, Any],
        job_id: UUID,
        api_key: str
    ) -> Dict[str, Any]:
        url = f"{self._base_url}/{model_name}:generateContent?key={api_key}"

        async with session.post(url, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise RuntimeError(f"HTTP {response.status}: {error_text}")

            data = await response.json()

            try:
                candidates = data.get("candidates", [])
                if not candidates:
                    raise ValueError("No candidates returned in response.")

                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if not parts:
                    raise ValueError("No parts found in response content.")

                raw_text = parts[0].get("text", "{}")
                return json.loads(raw_text)

            except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
                raise ValueError(f"Failed to parse JSON response from {model_name}: {str(e)}") from e