# File: systems/glossary/manager.py
from __future__ import annotations

import json
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class GlossaryManager:
    """Manages the custom translation glossary stored as a JSON txt file."""
    
    def __init__(self, file_path: str = "data/glossary.txt") -> None:
        self._file_path = file_path
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        if not os.path.exists(self._file_path):
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=4)

    async def save_glossary(self, file_bytes: bytes) -> bool:
        try:
            content = file_bytes.decode("utf-8")
            data = json.loads(content)
            
            if not isinstance(data, dict):
                logger.error("Glossary JSON is not a dictionary.")
                return False
                
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            logger.info("Glossary updated successfully.")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format for glossary: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to save glossary: {e}")
            return False

    async def load_glossary(self) -> Optional[Dict[str, Any]]:
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load glossary: {e}")
            return None

    def get_file_path(self) -> str:
        return self._file_path