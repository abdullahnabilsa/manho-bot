# systems/translation_pipeline/validators/default_validator.py
from __future__ import annotations

import logging
from typing import Any, Dict, List
from uuid import UUID
from pydantic import ValidationError

from systems.translation_pipeline.models.element import Element
from systems.translation_pipeline.models.page_data import Metadata, PageData
from systems.translation_pipeline.models.page_job import PageJob
from systems.translation_pipeline.models.scene import Scene

logger = logging.getLogger(__name__)

ALLOWED_ELEMENT_KEYS = {"element_number", "type", "speaker", "original", "translation", "alternative", "reason"}
ALLOWED_SCENE_KEYS = {"scene_number", "environment", "elements"}

class DefaultValidator:
    async def validate_and_update_job(self, job: PageJob, raw_json: Dict[str, Any]) -> PageJob:
        job_id = job.job_id
        logger.info(f"JobID={job_id} | Starting JSON validation")

        try:
            raw_metadata = raw_json.get("metadata", {})
            if not isinstance(raw_metadata, dict): raw_metadata = {}
            metadata = Metadata(
                model=raw_metadata.get("model"),
                page=raw_metadata.get("page", 1),
                total_pages=raw_metadata.get("total_pages", 1),
                scene_count=raw_metadata.get("scene_count", 0)
            )

            raw_scenes = raw_json.get("scenes", [])
            if not isinstance(raw_scenes, list): raw_scenes = []

            sanitized_scenes: List[Scene] = []

            for s_idx, raw_scene in enumerate(raw_scenes):
                try:
                    if not isinstance(raw_scene, dict): continue
                    scene_number = raw_scene.get("scene_number", s_idx + 1)
                    environment = raw_scene.get("environment")
                    raw_elements = raw_scene.get("elements", [])
                    if not isinstance(raw_elements, list): raw_elements = []

                    sanitized_elements: List[Element] = []
                    for e_idx, raw_elem in enumerate(raw_elements):
                        try:
                            clean_dict = self._sanitize_element(raw_elem, e_idx, job_id)
                            clean_dict["element_number"] = clean_dict.get("element_number", e_idx + 1)
                            element = Element(**clean_dict)
                            sanitized_elements.append(element)
                        except ValidationError as ve:
                            salvaged = self._salvage_element(clean_dict, ve)
                            if salvaged: sanitized_elements.append(salvaged)

                    scene = Scene(scene_number=scene_number, environment=environment, elements=sanitized_elements)
                    sanitized_scenes.append(scene)
                except Exception as scene_e:
                    logger.warning(f"JobID={job_id} | Scene {s_idx} failed: {scene_e}")

            page_data = PageData(metadata=metadata, scenes=sanitized_scenes)
            job.page_data = page_data
            logger.info(f"JobID={job_id} | Validation successful. Scenes: {len(page_data.scenes)}")
            return job

        except Exception as e:
            logger.error(f"JobID={job_id} | Critical validation failure: {e}", exc_info=True)
            job.page_data = PageData() 
            return job

    def _sanitize_element(self, raw_elem: Any, idx: int, job_id: UUID) -> Dict[str, Any]:
        if not isinstance(raw_elem, dict): return {}
        clean_dict: Dict[str, Any] = {}
        for key, value in raw_elem.items():
            lower_key = key.lower()
            if lower_key in ALLOWED_ELEMENT_KEYS:
                clean_dict[lower_key] = value if value != "" else None
        return clean_dict

    def _salvage_element(self, clean_dict: Dict[str, Any], ve: ValidationError) -> Element:
        salvage_dict = clean_dict.copy()
        for error in ve.errors():
            loc = error.get("loc", [])
            if loc and isinstance(loc, tuple) and len(loc) > 0:
                field = loc[0]
                if field in ALLOWED_ELEMENT_KEYS:
                    salvage_dict[field] = None
        try: return Element(**salvage_dict)
        except Exception: return Element()