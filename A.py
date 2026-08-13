import os

# قائمة بالملفات المحددة التي تريد جمع كودها فقط (بناءً على شجرة manho_bot)
files_to_read = [
    "config/__init__.py",
    "config/settings.py",
    "main.py",
    "pyproject.toml",
    "requirements.txt",
    "shared/__init__.py",
    "shared/container.py",
    "shared/database.py",
    "shared/event_bus.py",
    "shared/exceptions.py",
    "shared/logger.py",
    "systems/__init__.py",
    "systems/access_control/__init__.py",
    "systems/access_control/api_key_manager.py",
    "systems/access_control/manager.py",
    "systems/access_control/middleware.py",
    "systems/access_control/user_settings.py",
    "systems/ai_engine/__init__.py",
    "systems/ai_engine/base.py",
    "systems/ai_engine/exceptions.py",
    "systems/ai_engine/gemini.py",
    "systems/delivery/__init__.py",
    "systems/delivery/batch.py",
    "systems/delivery/image_optimizer.py",
    "systems/delivery/notifier.py",
    "systems/delivery/pipeline.py",
    "systems/delivery/renderers/__init__.py",
    "systems/delivery/renderers/message_builder.py",
    "systems/delivery/renderers/paginator.py",
    "systems/delivery/renderers/telegram.py",
    "systems/delivery/senders/__init__.py",
    "systems/delivery/senders/base.py",
    "systems/delivery/senders/strategies/__init__.py",
    "systems/delivery/senders/strategies/base.py",
    "systems/delivery/senders/strategies/grouped_session.py",
    "systems/delivery/senders/strategies/individual_session.py",
    "systems/delivery/ui/__init__.py",
    "systems/delivery/ui/handlers/__init__.py",
    "systems/delivery/ui/handlers/access.py",
    "systems/delivery/ui/handlers/admin.py",
    "systems/delivery/ui/handlers/api_keys.py",
    "systems/delivery/ui/handlers/messages.py",
    "systems/delivery/ui/handlers/session.py",
    "systems/delivery/ui/handlers/settings.py",
    "systems/delivery/ui/handlers/start.py",
    "systems/delivery/ui/keyboards.py",
    "systems/delivery/ui/middlewares.py",
    "systems/delivery/utils.py",
    "systems/glossary/__init__.py",
    "systems/glossary/manager.py",
    "systems/job_orchestration/__init__.py",
    "systems/job_orchestration/contracts.py",
    "systems/job_orchestration/queue.py",
    "systems/job_orchestration/worker.py",
    "systems/translation_pipeline/__init__.py",
    "systems/translation_pipeline/base_persona.py",
    "systems/translation_pipeline/models/__init__.py",
    "systems/translation_pipeline/models/element.py",
    "systems/translation_pipeline/models/page_data.py",
    "systems/translation_pipeline/models/page_job.py",
    "systems/translation_pipeline/models/panel_data.py",
    "systems/translation_pipeline/models/scene.py",
    "systems/translation_pipeline/models/script_data.py",
    "systems/translation_pipeline/plugins/__init__.py",
    "systems/translation_pipeline/plugins/default_translator/__init__.py",
    "systems/translation_pipeline/plugins/default_translator/persona.py",
    "systems/translation_pipeline/plugins/default_translator/prompt.txt",
    "systems/translation_pipeline/plugins/default_translator/templates/__init__.py",
    "systems/translation_pipeline/plugins/default_translator/templates/element_layout_template.txt",
    "systems/translation_pipeline/plugins/default_translator/templates/scene_header_template.txt",
    "systems/translation_pipeline/plugins/nabil/__init__.py",
    "systems/translation_pipeline/plugins/nabil/persona.py",
    "systems/translation_pipeline/plugins/nabil/prompt.txt",
    "systems/translation_pipeline/plugins/panel_translator/__init__.py",
    "systems/translation_pipeline/plugins/panel_translator/persona.py",
    "systems/translation_pipeline/plugins/panel_translator/prompt.txt",
    "systems/translation_pipeline/plugins/panel_translator/templates/__init__.py",
    "systems/translation_pipeline/plugins/panel_translator/templates/panel_element_layout_template.txt",
    "systems/translation_pipeline/plugins/panel_translator/templates/panel_header_template.txt",
    "systems/translation_pipeline/registry.py",
    "systems/translation_pipeline/validators/__init__.py",
    "systems/translation_pipeline/validators/default_validator.py",
    "utils/__init__.py",
    "utils/file_generator.py",
    "utils/image_optimizer.py",
    "utils/markdown_escaper.py",
    "utils/progress_bar.py",
    "utils/regex_template_engine.py"
]

# اسم الملف النهائي الذي سيحتوي على جميع الأكواد
output_file = 'manho_bot_all_code.txt'

# فتح الملف النصي للكتابة
with open(output_file, 'w', encoding='utf-8') as outfile:
    for filepath in files_to_read:
        # التحقق من أن الملف موجود
        if os.path.exists(filepath):
            # كتابة عنوان يوضح مسار واسم الملف
            outfile.write(f"\n{'='*80}\n")
            outfile.write(f"File: {filepath}\n")
            outfile.write(f"{'='*80}\n\n")
            
            # قراءة محتوى الملف ولصقه داخل الملف النصي
            try:
                with open(filepath, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    outfile.write(content)
                    # التأكد من وجود سطر فارغ بعد كل كود
                    if not content.endswith('\n'):
                        outfile.write('\n')
                print(f"تمت إضافة كود: {filepath}")
            except Exception as e:
                outfile.write(f"[حدث خطأ أثناء قراءة الملف: {e}]\n")
                print(f"خطأ في قراءة: {filepath}")
        else:
            outfile.write(f"\n{'='*80}\n")
            outfile.write(f"File: {filepath} (الملف غير موجود)\n")
            outfile.write(f"{'='*80}\n\n")
            print(f"تنبيه: الملف غير موجود: {filepath}")

print(f"\nتم الانتهاء! تم تجميع جميع الأكواد في ملف: {output_file}")