# systems/delivery/renderers/message_builder.py
from __future__ import annotations

import os
from typing import ClassVar

from systems.translation_pipeline.models.element import Element
from systems.translation_pipeline.models.scene import Scene
from utils.markdown_escaper import escape_markdown_v2
from utils.regex_template_engine import RegexTemplateEngine


class SafeElementContext:
    def __init__(self, elem: Element) -> None:
        self.element_number = elem.element_number
        self.type = elem.type
        self.speaker = escape_markdown_v2(elem.speaker) if elem.speaker else None
        self.original = escape_markdown_v2(elem.original) if elem.original else None
        self.translation = escape_markdown_v2(elem.translation) if elem.translation else None
        self.alternative = escape_markdown_v2(elem.alternative) if elem.alternative else None
        self.reason = escape_markdown_v2(elem.reason) if elem.reason else None

class SafeSceneContext:
    def __init__(self, scene: Scene) -> None:
        self.scene_number = scene.scene_number
        self.environment = escape_markdown_v2(scene.environment) if scene.environment else None

class MessageBuilder:
    MAX_LENGTH = 3500
    HEADER_TEMPLATE = (
        "📖 ترجمة المانهوا\n"
        "📄 الملف: {file_name}\n"
        "الرسالة: {msg_num} من [[TOTAL_MSGS]]\n"
        "━━━━━━━━━━━━━━━\n"
    )
    CONTINUATION_MARKER = "Scene \\(Continued\\)\n\n"
    FOOTER_NEXT = "\n\n━━━━━━━━━━━━━━━\nانتهى الجزء\nيتبع\\.\\.\\."
    FOOTER_END = "\n\n━━━━━━━━━━━━━━━\nاكتملت ترجمة الصفحة\\."

    _scene_template: ClassVar[str] = ""
    _element_template: ClassVar[str] = ""
    _templates_loaded: ClassVar[bool] = False

    @classmethod
    def _load_templates(cls) -> None:
        if not cls._templates_loaded:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            plugins_dir = os.path.join(base_dir, "..", "..", "translation_pipeline", "plugins", "default_translator", "templates")
            scene_path = os.path.join(plugins_dir, "scene_header_template.txt")
            elem_path = os.path.join(plugins_dir, "element_layout_template.txt")
            
            with open(scene_path, "r", encoding="utf-8") as f:
                cls._scene_template = f.read()
            with open(elem_path, "r", encoding="utf-8") as f:
                cls._element_template = f.read()
            cls._templates_loaded = True

    def __init__(self, page_num: int, msg_num: int, is_continuation: bool, file_name: str = "Unknown") -> None:
        self._load_templates()
        self.page_num = page_num
        self.msg_num = msg_num
        self.is_continuation = is_continuation
        self._buffer = ""
        self.file_name = escape_markdown_v2(file_name) if file_name else "Unknown"

    def _get_header(self) -> str:
        return self.HEADER_TEMPLATE.format(file_name=self.file_name, msg_num=self.msg_num)

    def _get_footer(self, is_last_message: bool) -> str:
        return self.FOOTER_END if is_last_message else self.FOOTER_NEXT

    def format_scene_header(self, scene: Scene) -> str:
        ctx = SafeSceneContext(scene)
        engine = RegexTemplateEngine(self._scene_template)
        return engine.render(ctx) + "\n"

    def format_element(self, elem: Element) -> str:
        ctx = SafeElementContext(elem)
        engine = RegexTemplateEngine(self._element_template)
        return engine.render(ctx) + "\n"

    def can_fit(self, text_to_add: str) -> bool:
        if not text_to_add:
            return True
        projected_length = (
            len(self._get_header())
            + len(self.CONTINUATION_MARKER if self.is_continuation else "")
            + len(self._buffer)
            + len(text_to_add)
            + len(self.FOOTER_NEXT)
        )
        return projected_length <= self.MAX_LENGTH

    def append_to_buffer(self, text: str) -> None:
        if text:
            self._buffer += text

    def build(self, is_last_message: bool) -> str:
        header = self._get_header()
        continuation = self.CONTINUATION_MARKER if self.is_continuation else ""
        footer = self._get_footer(is_last_message)
        return f"{header}{continuation}{self._buffer}{footer}"