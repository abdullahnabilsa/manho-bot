# utils/regex_template_engine.py
from __future__ import annotations

import re
from typing import Any

class RegexTemplateEngine:
    _IF_PATTERN = re.compile(r"\{\{#if (\w+)\}\}(.*?)\{\{/if\}\}", re.DOTALL)
    _VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")

    def __init__(self, template: str) -> None:
        self.template = template

    def render(self, context: Any) -> str:
        text = self.template
        
        def replace_conditional(match: re.Match) -> str:
            var_name = match.group(1)
            content = match.group(2)
            if isinstance(context, dict):
                val = context.get(var_name)
            else:
                val = getattr(context, var_name, None)
            if val:
                return content.strip()
            return ""
            
        text = self._IF_PATTERN.sub(replace_conditional, text)
        
        def replace_variable(match: re.Match) -> str:
            var_name = match.group(1)
            if isinstance(context, dict):
                val = context.get(var_name, "")
            else:
                val = getattr(context, var_name, "")
            return str(val) if val is not None else ""
            
        text = self._VAR_PATTERN.sub(replace_variable, text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()