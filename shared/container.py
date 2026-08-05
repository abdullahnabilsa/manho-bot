# File: shared/container.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.database import Database
    from shared.event_bus import EventBus
    from systems.access_control.manager import AccessManager
    from systems.access_control.api_key_manager import APIKeyManager
    from systems.access_control.user_settings import UserSettingsManager
    from systems.ai_engine.base import BaseAIProvider
    from systems.translation_pipeline.registry import PersonaRegistry
    from systems.job_orchestration.queue import AsyncSingleWorkerQueue
    from systems.job_orchestration.worker import JobManager
    from systems.job_orchestration.concurrency.manager import ConcurrencyManager
    from systems.delivery.batch import BatchManager
    from systems.delivery.renderers.telegram import TelegramRenderer
    from systems.delivery.pipeline import DeliveryPipeline
    from systems.delivery.notifier import BotErrorNotifier
    from systems.glossary.manager import GlossaryManager
    from telegram import Bot

@dataclass
class ServiceContainer:
    """Typed dependency injection container."""
    db: "Database"
    bot: "Bot"
    event_bus: "EventBus"
    
    access: "AccessManager"
    api_keys: "APIKeyManager"
    settings: "UserSettingsManager"
    
    ai: "BaseAIProvider"
    personas: "PersonaRegistry"
    
    queue: "AsyncSingleWorkerQueue"
    jobs: "JobManager"
    concurrency: "ConcurrencyManager"
    
    batch: "BatchManager"
    renderer: "TelegramRenderer"
    delivery: "DeliveryPipeline"
    notifier: "BotErrorNotifier"
    
    glossary: "GlossaryManager"