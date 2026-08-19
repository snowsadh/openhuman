from __future__ import annotations

import re


def sanitize_filename(raw: str | None) -> str:
    """Strip path separators and null bytes to prevent traversal."""
    if not raw:
        return "upload"
    # Take only the basename (strips any directory components)
    safe = raw.replace("\\", "/").split("/")[-1]
    # Remove null bytes and leading dots that could represent hidden files
    safe = safe.replace("\x00", "").lstrip(".")
    # Collapse to alphanumeric + safe punctuation, max 255 chars
    safe = re.sub(r"[^\w.\-]", "_", safe)[:255]
    return safe or "upload"
