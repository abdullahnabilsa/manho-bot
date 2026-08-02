# systems/translation_pipeline/models/scene.py
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from systems.translation_pipeline.models.element import Element

class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    scene_number: Optional[int] = Field(default=None)
    environment: Optional[str] = Field(default=None)
    elements: List[Element] = Field(default_factory=list)