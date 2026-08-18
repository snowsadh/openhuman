import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_within_dir(path: Path, root: Path) -> str | None:
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
    except (ValueError, OSError) as exc:
        return f"Path escapes allowed directory: {exc}"
    return None


def has_traversal_component(path_str: str) -> bool:
    parts = Path(path_str).parts
    return ".." in parts
