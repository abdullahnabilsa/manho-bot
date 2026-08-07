# systems/translation_pipeline/base_persona.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import io
import os
import sys

from systems.translation_pipeline.models.page_job import PageJob
from systems.translation_pipeline.models.page_data import PageData


class BasePersona(ABC):
    name: str = "Base Persona"

    @property
    def module_dir(self) -> str:
        module = sys.modules[self.__class__.__module__]
        return os.path.dirname(os.path.abspath(module.__file__))

    @property
    def prompt(self) -> str:
        prompt_path = os.path.join(self.module_dir, "prompt.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    @abstractmethod
    async def validate_and_update_job(self, job: PageJob, raw_json: Dict[str, Any]) -> PageJob: pass

    @abstractmethod
    async def paginate(self, job: PageJob, mode: str = "scene_split") -> List[str]: pass

    @abstractmethod
    def generate_txt(self, pages: List[PageData], session_note: Optional[str] = None) -> io.BytesIO: pass

    @abstractmethod
    def generate_docx(self, pages: List[PageData], session_note: Optional[str] = None) -> io.BytesIO: pass