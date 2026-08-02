# systems/translation_pipeline/models/element.py
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class Element(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )
    element_number: Optional[int] = Field(default=None)
    type: Optional[str] = Field(default=None)
    speaker: Optional[str] = Field(default=None)
    original: Optional[str] = Field(default=None)
    translation: Optional[str] = Field(default=None)
    alternative: Optional[str] = Field(default=None)
    reason: Optional[str] = Field(default=None)