# systems/translation_pipeline/registry.py
from __future__ import annotations

import importlib
import inspect
import logging
import os
import sys
from typing import Dict, List

from systems.translation_pipeline.base_persona import BasePersona

logger = logging.getLogger(__name__)

class PersonaRegistry:
    def __init__(self, plugins_dir: str = "systems/translation_pipeline/plugins") -> None:
        self._handlers: Dict[str, BasePersona] = {}
        self._plugins_dir = os.path.abspath(plugins_dir)
        self._discover_personas()

    def _discover_personas(self) -> None:
        if not os.path.isdir(self._plugins_dir):
            logger.error(f"Plugins directory not found: {self._plugins_dir}")
            return

        for module_name in os.listdir(self._plugins_dir):
            module_path = os.path.join(self._plugins_dir, module_name)
            if os.path.isdir(module_path) and not module_name.startswith('_'):
                try:
                    full_module_name = f"systems.translation_pipeline.plugins.{module_name}.persona"
                    module = importlib.import_module(full_module_name)
                    
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BasePersona) and obj is not BasePersona:
                            instance = obj()
                            self._handlers[instance.name.lower()] = instance
                            logger.info(f"Successfully loaded persona plugin: {instance.name}")
                except Exception as e:
                    logger.error(f"Failed to load persona from {module_name}: {e}", exc_info=True)

        if "default translator" not in self._handlers:
            logger.critical("Default Translator persona failed to load! Fallback mechanism disabled.")

    def get_handler(self, persona_name: str) -> BasePersona:
        if not persona_name:
            return self._handlers.get("default translator")
        for key, handler in self._handlers.items():
            if key == persona_name.lower():
                return handler
        return self._handlers.get("default translator")

    def get_available_personas(self) -> List[str]:
        return [p.name for p in self._handlers.values()]