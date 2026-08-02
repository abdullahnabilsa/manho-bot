# systems/translation_pipeline/models/page_job.py
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field
from systems.translation_pipeline.models.page_data import PageData

class JobState(str, Enum):
    WAITING = "waiting"
    PROCESSING = "processing"
    RENDERING = "rendering"
    SENDING = "sending"
    FINISHED = "finished"
    FAILED = "failed"

class MessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_index: int
    total_pages: int
    text: str
    parse_mode: Optional[str] = "MarkdownV2"
    reply_markup: Optional[Any] = None
    message_id: Optional[int] = None

class PageJob(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )
    job_id: UUID = Field(default_factory=uuid4)
    user_id: int
    chat_id: int
    state: JobState = JobState.WAITING
    
    image_file_id: Optional[str] = None
    image_bytes: Optional[bytes] = None
    file_name: Optional[str] = None
    page_data: Optional[PageData] = None
    message_payloads: List[MessagePayload] = Field(default_factory=list)
    
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    photo_message_id: Optional[int] = None
    status_message_id: Optional[int] = None