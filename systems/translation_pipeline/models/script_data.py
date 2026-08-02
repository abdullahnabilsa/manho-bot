# systems/translation_pipeline/models/script_data.py
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field

class ScriptPageData(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    script: str = Field(default="")
    file_name: str = Field(default=None)