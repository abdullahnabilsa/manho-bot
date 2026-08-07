# systems/translation_pipeline/plugins/default_translator/persona.py
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from systems.translation_pipeline.base_persona import BasePersona
from systems.translation_pipeline.models.page_job import PageJob
from systems.translation_pipeline.models.page_data import PageData
from systems.translation_pipeline.validators.default_validator import DefaultValidator

# Renderers are part of the Delivery system, but imported here for presentation logic
from systems.delivery.renderers.paginator import Paginator
from utils.file_generator import FileGenerator


class DefaultPersona(BasePersona):
    name = "Default Translator"

    def __init__(self) -> None:
        self._validator = DefaultValidator()
        self._paginator = Paginator()

    async def validate_and_update_job(self, job: PageJob, raw_json: Dict[str, Any]) -> PageJob:
        return await self._validator.validate_and_update_job(job, raw_json)

    async def paginate(self, job: PageJob, mode: str = "scene_split") -> List[str]:
        return await self._paginator.paginate(job, page_num=1, mode=mode)

    def generate_txt(self, pages: List[PageData], session_note: Optional[str] = None) -> io.BytesIO:
        return FileGenerator.generate_txt(pages, session_note)

    def generate_docx(self, pages: List[PageData], session_note: Optional[str] = None) -> io.BytesIO:
        return FileGenerator.generate_docx(pages, session_note)