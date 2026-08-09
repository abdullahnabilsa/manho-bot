# systems/glossary/manager.py
from __future__ import annotations

import logging
import os
import time
from typing import Dict, Any, Optional

try:
    import orjson
    USE_ORJSON = True
except ImportError:
    import json
    USE_ORJSON = False

logger = logging.getLogger(__name__)

class GlossaryManager:
    """Manages the custom translation glossary with In-Memory Caching."""
    
    def __init__(self, file_path: str = "data/glossary.txt") -> None:
        self._file_path = file_path
        self._cache: Optional[Dict[str, Any]] = None
        self._last_mtime: float = 0.0
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        if not os.path.exists(self._file_path):
            with open(self._file_path, "wb") as f:
                if USE_ORJSON:
                    f.write(orjson.dumps({}, option=orjson.OPT_INDENT_2))
                else:
                    f.write(json.dumps({}, ensure_ascii=False, indent=4).encode('utf-8'))

    async def save_glossary(self, file_bytes: bytes) -> bool:
        try:
            if USE_ORJSON:
                data = orjson.loads(file_bytes)
            else:
                data = json.loads(file_bytes.decode("utf-8"))
            
            if not isinstance(data, dict):
                logger.error("Glossary JSON is not a dictionary.")
                return False
                
            with open(self._file_path, "wb") as f:
                if USE_ORJSON:
                    f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
                else:
                    f.write(json.dumps(data, ensure_ascii=False, indent=4).encode('utf-8'))
            
            self._cache = data
            self._last_mtime = os.path.getmtime(self._file_path)
            logger.info("Glossary updated and cached successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to save glossary: {e}")
            return False

    async def load_glossary(self) -> Optional[Dict[str, Any]]:
        try:
            current_mtime = os.path.getmtime(self._file_path)
            if self._cache is not None and current_mtime == self._last_mtime:
                return self._cache
                
            with open(self._file_path, "rb") as f:
                if USE_ORJSON:
                    self._cache = orjson.loads(f.read())
                else:
                    self._cache = json.load(f)
            self._last_mtime = current_mtime
            return self._cache
        except Exception as e:
            logger.error(f"Failed to load glossary: {e}")
            return None

    def get_file_path(self) -> str:
        return self._file_path