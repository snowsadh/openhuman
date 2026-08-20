"""File manipulation tools for AI employees.

Simplified version of Hermes' file_operations + file_tools, using direct
Python I/O instead of shell commands / terminal backends.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".tif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".m4v", ".mpeg", ".mpg",
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma", ".aiff", ".opus",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz", ".z", ".tgz", ".iso",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".obj", ".lib",
    ".app", ".msi", ".deb", ".rpm",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".pyc", ".pyo", ".class", ".jar", ".war", ".ear", ".node", ".wasm", ".rlib",
    ".sqlite", ".sqlite3", ".db", ".mdb", ".idx",
    ".psd", ".ai", ".eps", ".sketch", ".fig", ".xd", ".blend", ".3ds", ".max",
    ".swf", ".fla",
    ".lockb", ".dat", ".data",
})

MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_READ_LINES = 2000
MAX_LINE_LENGTH = 2000

# Paths that file tools must never write to
WRITE_DENIED_PREFIXES = [
    "/etc/",
    "/boot/",
    "/usr/lib/",
    "/var/lib/",
    "/private/etc/",
    str(Path.home() / ".ssh"),
    str(Path.home() / ".aws"),
    str(Path.home() / ".gnupg"),
    str(Path.home() / ".kube"),
    str(Path.home() / ".docker"),
    str(Path.home() / ".config"),
    str(Path.home() / ".git-credentials"),
]

WRITE_DENIED_EXACT = {
    str(Path.home() / ".netrc"),
    str(Path.home() / ".pgpass"),
    str(Path.home() / ".npmrc"),
    str(Path.home() / ".pypirc"),
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
}


def _has_binary_extension(path: str) -> bool:
    dot = path.rfind(".")
    if dot == -1:
        return False
    return path[dot:].lower() in BINARY_EXTENSIONS


def _is_likely_binary(content: bytes) -> bool:
    null_bytes = content.count(b"\x00")
    return null_bytes / max(len(content), 1) > 0.05


def _check_write_safe(path: str) -> str | None:
    resolved = os.path.realpath(os.path.expanduser(path))
    for prefix in WRITE_DENIED_PREFIXES:
        if resolved.startswith(prefix):
            return f"Refusing to write to sensitive path: {path}"
    if resolved in WRITE_DENIED_EXACT:
        return f"Refusing to write to sensitive path: {path}"
    return None


def _add_line_numbers(content: str, start: int = 1) -> str:
    lines = content.split("\n")
    out = []
    for i, line in enumerate(lines, start=start):
        if len(line) > MAX_LINE_LENGTH:
            line = line[:MAX_LINE_LENGTH] + "... [truncated]"
        out.append(f"{i}|{line}")
    return "\n".join(out)


def _detect_line_ending(sample: str) -> str:
    if not sample:
        return "\n"
    head = sample[:4096]
    if "\r\n" in head:
        return "\r\n"
    return "\n"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def file_read(
    path: str,
    offset: int = 1,
    limit: int = 500,
) -> str:
    """Read a file from the filesystem with line numbers and pagination.

    Args:
        path: Absolute or relative path to the file.
        offset: Line number to start from (1-indexed, default 1).
        limit: Maximum number of lines to return (default 500, max 2000).
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return f"Error: File not found: {path}"
    if not resolved.is_file():
        return f"Error: Not a file: {path}"

    if _has_binary_extension(path):
        return f"Error: Cannot read binary file: {path}"

    file_size = resolved.stat().st_size
    if file_size > MAX_FILE_SIZE:
        return f"Error: File exceeds {MAX_FILE_SIZE // 1024 // 1024} MB size limit."

    try:
        data = resolved.read_bytes()
    except PermissionError:
        return f"Error: Permission denied reading: {path}"
    except OSError as e:
        return f"Error reading file: {e}"

    if _is_likely_binary(data):
        return f"Error: Binary file detected: {path}"

    text = data.decode("utf-8", errors="replace")
    end = offset - 1 + limit
    lines = text.split("\n")
    total = len(lines)
    selected = lines[offset - 1 : end]
    content = "\n".join(selected)
    numbered = _add_line_numbers(content, start=offset)
    truncated = total > end
    hint = (
        f" [Use offset={end + 1} to continue — showing {offset}-{min(end, total)} of {total} lines]"
        if truncated
        else ""
    )
    return f"{numbered}\n{hint}".strip()


@tool
def file_write(
    path: str,
    content: str,
) -> str:
    """Write or overwrite a file on the filesystem.

    Creates parent directories if they don't exist.

    Args:
        path: Absolute or relative path to write to.
        content: Text content to write.
    """
    err = _check_write_safe(path)
    if err:
        return err

    resolved = Path(path).expanduser().resolve()
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        size = resolved.stat().st_size
        return f"Successfully wrote {size} bytes to {resolved}"
    except PermissionError:
        return f"Error: Permission denied writing to: {path}"
    except OSError as e:
        return f"Error writing file: {e}"


@tool
def file_search(
    pattern: str,
    path: str = ".",
    file_glob: str | None = None,
    max_results: int = 50,
) -> str:
    """Search for a regex pattern in files.

    Args:
        pattern: Regular expression to search for.
        path: Directory to search in (default: current directory).
        file_glob: Optional file glob pattern (e.g. '*.py', '*.{ts,js}').
        max_results: Maximum matches to return (default 50).
    """
    search_dir = Path(path).expanduser().resolve()
    if not search_dir.exists():
        return f"Error: Path not found: {path}"
    if not search_dir.is_dir():
        return f"Error: Not a directory: {path}"

    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"Error: Invalid regex: {e}"

    matches: list[tuple[str, int, str]] = []
    kwargs: dict = {}
    if file_glob:
        kwargs["glob"] = file_glob

    for fpath in search_dir.rglob("*"):
        if max_results and len(matches) >= max_results:
            break
        if not fpath.is_file():
            continue
        if _has_binary_extension(fpath.name):
            continue
        try:
            if file_glob and not fpath.match(file_glob):
                continue
        except (ValueError, IndexError):
            pass
        try:
            for i, line in enumerate(fpath.read_text("utf-8", errors="replace").split("\n"), 1):
                if compiled.search(line):
                    matches.append((str(fpath.relative_to(search_dir)), i, line.strip()))
                    if max_results and len(matches) >= max_results:
                        break
        except (PermissionError, OSError):
            continue

    if not matches:
        return f"No matches found for pattern: {pattern}"

    lines = [f"Found {len(matches)} match(es) in {search_dir}:", ""]
    current: str | None = None
    for filepath, lineno, line in matches:
        if filepath != current:
            lines.append(filepath)
            current = filepath
        lines.append(f"  {lineno}: {line}")
    return "\n".join(lines)


@tool
def file_patch(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Replace text in a file using exact string matching.

    Args:
        path: Path to the file to patch.
        old_string: Text to search for (must match exactly).
        new_string: Replacement text.
        replace_all: Replace all occurrences instead of just the first.
    """
    err = _check_write_safe(path)
    if err:
        return err

    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return f"Error: File not found: {path}"

    try:
        text = resolved.read_text("utf-8")
    except (PermissionError, OSError) as e:
        return f"Error reading file: {e}"

    if old_string not in text:
        return (
            "Error: old_string not found in file. "
            "Note: the match must be exact — use file_read first to verify the content."
        )

    original_le = _detect_line_ending(text)
    new_normalized = new_string.replace("\r\n", "\n").replace("\r", "\n")
    if original_le != "\n":
        new_normalized = new_normalized.replace("\n", original_le)

    if replace_all:
        new_text = text.replace(old_string, new_string)
    else:
        new_text = text.replace(old_string, new_string, 1)

    try:
        resolved.write_text(new_text, encoding="utf-8")
        return f"Successfully patched {resolved}"
    except (PermissionError, OSError) as e:
        return f"Error writing file: {e}"


@tool
def file_delete(path: str) -> str:
    """Delete a file from the filesystem.

    Args:
        path: Path to the file to delete.
    """
    err = _check_write_safe(path)
    if err:
        return err

    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return f"Error: File not found: {path}"
    if not resolved.is_file():
        return f"Error: Not a file: {path}"

    try:
        resolved.unlink()
        return f"Successfully deleted {resolved}"
    except (PermissionError, OSError) as e:
        return f"Error deleting file: {e}"
