# utils/image_optimizer.py
from __future__ import annotations

import io
import logging
from PIL import Image

logger = logging.getLogger(__name__)

def optimize_image(image_bytes: bytes) -> bytes:
    """Pure function to optimize an image for AI processing."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        max_size = 1280
        if max(img.width, img.height) > max_size:
            ratio = max_size / max(img.width, img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        return buffer.getvalue()
    except Exception as e:
        logger.warning(f"Image optimization failed, using original: {e}")
        return image_bytes