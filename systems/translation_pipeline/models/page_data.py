# systems/translation_pipeline/models/page_data.py
from __future__ import annotations
from typing import List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field
from systems.translation_pipeline.models.scene import Scene
from systems.translation_pipeline.models.panel_data import PanelPageData
from systems.translation_pipeline.models.script_data import ScriptPageData

class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Optional[str] = Field(default=None)
    page: Optional[int] = Field(default=None)
    total_pages: Optional[int] = Field(default=None)
    scene_count: Optional[int] = Field(default=None)

class PageData(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    metadata: Optional[Metadata] = Field(default=None)
    scenes: List[Scene] = Field(default_factory=list)
    file_name: Optional[str] = Field(default=None)
    custom_data: Optional[Union[PanelPageData, ScriptPageData]] = Field(default=None)