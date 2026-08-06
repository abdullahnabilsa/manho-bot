# utils/markdown_escaper.py
from __future__ import annotations

import re
from typing import Optional

def escape_markdown_v2(text: Optional[str]) -> str:
    if not text or not isinstance(text, str):
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

def escape_html(text: Optional[str]) -> str:
    """Escapes HTML special characters (&, <, >) to prevent injection in HTML parse mode."""
    if not text or not isinstance(text, str):
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def sanitize_filename(filename: Optional[str]) -> str:
    if not filename or not isinstance(filename, str):
        return "manga_translation"
    name = re.sub(r'\.(txt|docx|pdf)$', '', filename, flags=re.IGNORECASE)
    name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    if not name:
        return "manga_translation"
    return name[:50]