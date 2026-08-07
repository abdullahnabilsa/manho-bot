# File: utils/progress_bar.py
from __future__ import annotations

def generate_progress_bar(processed: int, total: int, length: int = 10) -> str:
    """Generates a text-based progress bar like [████████░░] 80%"""
    if total <= 0:
        return f"[{'░' * length}] 0%"
    
    percentage = min(100, int((processed / total) * 100))
    filled = int((percentage / 100) * length)
    bar = '█' * filled + '░' * (length - filled)
    return f"[{bar}] {percentage}%"