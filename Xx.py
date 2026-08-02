import os
from pathlib import Path

# قائمة بجميع مسارات الملفات المطلوبة للمشروع
FILES_TO_CREATE = [
    # الجذر
    "main.py",
    "pyproject.toml",
    "requirements.txt",
    ".env",

    # config
    "config/__init__.py",
    "config/settings.py",

    # shared
    "shared/__init__.py",
    "shared/database.py",
    "shared/exceptions.py",
    "shared/event_bus.py",
    "shared/logger.py",
    "shared/container.py",

    # utils
    "utils/__init__.py",
    "utils/markdown_escaper.py",
    "utils/regex_template_engine.py",
    "utils/file_generator.py",
    "utils/image_optimizer.py",

    # systems/__init__.py
    "systems/__init__.py",

    # System 1: Access Control
    "systems/access_control/__init__.py",
    "systems/access_control/manager.py",
    "systems/access_control/api_key_manager.py",
    "systems/access_control/user_settings.py",
    "systems/access_control/middleware.py",

    # System 2: Job Orchestration
    "systems/job_orchestration/__init__.py",
    "systems/job_orchestration/queue.py",
    "systems/job_orchestration/worker.py",
    "systems/job_orchestration/contracts.py",
    
    # Concurrency Sub-module
    "systems/job_orchestration/concurrency/__init__.py",
    "systems/job_orchestration/concurrency/db_store.py",
    "systems/job_orchestration/concurrency/locks.py",
    "systems/job_orchestration/concurrency/manager.py",
    "systems/job_orchestration/concurrency/exceptions.py",

    # System 3: AI Engine
    "systems/ai_engine/__init__.py",
    "systems/ai_engine/base.py",
    "systems/ai_engine/gemini.py",
    "systems/ai_engine/exceptions.py",

    # System 4: Translation Pipeline
    "systems/translation_pipeline/__init__.py",
    "systems/translation_pipeline/base_persona.py",
    "systems/translation_pipeline/registry.py",
    
    # Pipeline Models
    "systems/translation_pipeline/models/__init__.py",
    "systems/translation_pipeline/models/element.py",
    "systems/translation_pipeline/models/scene.py",
    "systems/translation_pipeline/models/page_data.py",
    "systems/translation_pipeline/models/page_job.py",
    "systems/translation_pipeline/models/panel_data.py",
    "systems/translation_pipeline/models/script_data.py",

    # Pipeline Validators
    "systems/translation_pipeline/validators/__init__.py",
    "systems/translation_pipeline/validators/default_validator.py",

    # Pipeline Plugins
    "systems/translation_pipeline/plugins/__init__.py",
    
    # Default Translator Plugin
    "systems/translation_pipeline/plugins/default_translator/__init__.py",
    "systems/translation_pipeline/plugins/default_translator/persona.py",
    "systems/translation_pipeline/plugins/default_translator/prompt.txt",
    "systems/translation_pipeline/plugins/default_translator/templates/scene_header_template.txt",
    "systems/translation_pipeline/plugins/default_translator/templates/element_layout_template.txt",
    
    # Nabil Plugin
    "systems/translation_pipeline/plugins/nabil/__init__.py",
    "systems/translation_pipeline/plugins/nabil/persona.py",
    "systems/translation_pipeline/plugins/nabil/prompt.txt",
    
    # Panel Translator Plugin
    "systems/translation_pipeline/plugins/panel_translator/__init__.py",
    "systems/translation_pipeline/plugins/panel_translator/persona.py",
    "systems/translation_pipeline/plugins/panel_translator/prompt.txt",
    "systems/translation_pipeline/plugins/panel_translator/templates/panel_header_template.txt",
    "systems/translation_pipeline/plugins/panel_translator/templates/panel_element_layout_template.txt",

    # System 5: Delivery
    "systems/delivery/__init__.py",
    "systems/delivery/pipeline.py",
    "systems/delivery/notifier.py",
    "systems/delivery/batch.py",
    "systems/delivery/utils.py",
    "systems/delivery/image_optimizer.py",
    
    # Senders
    "systems/delivery/senders/__init__.py",
    "systems/delivery/senders/base.py",
    "systems/delivery/senders/direct.py",
    "systems/delivery/senders/session.py",
    
    # Renderers
    "systems/delivery/renderers/__init__.py",
    "systems/delivery/renderers/message_builder.py",
    "systems/delivery/renderers/paginator.py",
    "systems/delivery/renderers/telegram.py",
    
    # UI
    "systems/delivery/ui/__init__.py",
    "systems/delivery/ui/keyboards.py",
    "systems/delivery/ui/middlewares.py",
    
    # UI Handlers
    "systems/delivery/ui/handlers/__init__.py",
    "systems/delivery/ui/handlers/start.py",
    "systems/delivery/ui/handlers/settings.py",
    "systems/delivery/ui/handlers/session.py",
    "systems/delivery/ui/handlers/messages.py",
    "systems/delivery/ui/handlers/access.py",
    "systems/delivery/ui/handlers/admin.py",
    "systems/delivery/ui/handlers/api_keys.py",
    "systems/delivery/ui/handlers/concurrency.py",
]

def create_project_structure():
    base_dir = Path.cwd()
    created_count = 0
    
    print("🚀 Starting creation of Manga Bot project structure...")
    
    for file_path in FILES_TO_CREATE:
        full_path = base_dir / file_path
        
        # إنشاء المجلدات إذا لم تكن موجودة
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # إنشاء الملف الفارغ إذا لم يكن موجوداً بالفعل
        if not full_path.exists():
            full_path.touch()
            print(f"✅ Created: {file_path}")
            created_count += 1
        else:
            print(f"⚠️ Already exists, skipped: {file_path}")
            
    print(f"\n🎉 Done! Successfully created {created_count} files.")
    print(f"Project structure is ready at: {base_dir}")

if __name__ == "__main__":
    create_project_structure()