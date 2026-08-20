"""Audio transcription tool for AI employees.

Transcribes audio files using a free Hugging Face Inference API model
(openai/whisper-large-v3 by default).
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from langchain_core.tools import tool

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {
    ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a",
    ".wav", ".webm", ".ogg", ".aac", ".flac",
}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
DEFAULT_MODEL = "openai/whisper-large-v3"
_HF_BASE = "https://api-inference.huggingface.co/models"


@tool
def transcribe_audio(
    file_path: str,
    model: str = DEFAULT_MODEL,
    language: str | None = None,
) -> str:
    """Transcribe an audio file to text using free Hugging Face Whisper.

    Args:
        file_path: Path to the audio file on the server.
        model: Hugging Face model ID (default: openai/whisper-large-v3).
        language: Optional language code (e.g. 'en', 'es', 'fr').
                  Auto-detected if omitted.
    """
    resolved = Path(file_path).expanduser().resolve()
    if not resolved.exists():
        return f"Error: File not found: {file_path}"
    if not resolved.is_file():
        return f"Error: Not a file: {file_path}"

    ext = resolved.suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        return (
            f"Error: Unsupported format '{ext}'. Supported: "
            + ", ".join(sorted(SUPPORTED_FORMATS))
        )

    file_size = resolved.stat().st_size
    if file_size > MAX_FILE_SIZE:
        return f"Error: File exceeds {MAX_FILE_SIZE // 1024 // 1024} MB limit."

    api_key = settings.huggingface_api_key
    if not api_key:
        return (
            "Error: HUGGINGFACE_API_KEY not configured. "
            "Get a free token at https://huggingface.co/settings/tokens"
        )

    url = f"{_HF_BASE}/{model}"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {}
    if language:
        params = {"parameters": {"language": language}}

    try:
        with open(resolved, "rb") as audio_file:
            data = audio_file.read()

        with httpx.Client(timeout=120) as client:
            resp = client.post(url, headers=headers, data=data, params=params)
            resp.raise_for_status()
            result = resp.json()

        if isinstance(result, list):
            text = result[0].get("text", "")
        elif isinstance(result, dict):
            text = result.get("text", "")
        else:
            text = str(result)

        return text.strip() or "(empty transcription)"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 503:
            return (
                f"Model {model} is loading on Hugging Face. "
                "Please try again in a few seconds."
            )
        return f"Transcription failed (HTTP {e.response.status_code}): {e.response.text[:300]}"
    except Exception as e:
        logger.exception("Transcription failed")
        return f"Transcription failed: {e}"
