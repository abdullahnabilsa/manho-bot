# systems/translation_pipeline/models/panel_data.py
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class TranslationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    source_language: Optional[str] = Field(default=None)
    target_language: Optional[str] = Field(default=None)
    style: Optional[str] = Field(default=None)

class PanelElement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)
    type: Optional[str] = Field(default=None)
    character: Optional[str] = Field(default=None)
    original_text: Optional[str] = Field(default=None)
    translated_text: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)

class Panel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    panel_index: Optional[int] = Field(default=None)
    elements: List[PanelElement] = Field(default_factory=list)

class PanelPageData(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    translation_metadata: Optional[TranslationMetadata] = Field(default=None)
    panels: List[Panel] = Field(default_factory=list)
    file_name: Optional[str] = Field(default=None)