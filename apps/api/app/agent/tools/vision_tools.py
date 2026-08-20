"""Image analysis tool for agents.

Downloads an image from a URL and sends it to a free Hugging Face
Inference API vision model (BLIP VQA by default) for analysis.
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO

import httpx
from langchain_core.tools import tool
from PIL import Image

from app.agent.tools.executor import _validate_url
from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_IMAGE_SIZE = 4 * 1024 * 1024  # 4 MB
_MAX_DIMENSION = 7900
DEFAULT_MODEL = "Salesforce/blip-vqa-base"
_HF_BASE = "https://api-inference.huggingface.co/models"


def _validate_image_url(url: str) -> tuple[str | None, str | None]:
    """Validate image URL. Returns ``(error, safe_url)``."""
    err = _validate_url(url)
    if err:
        return f"Cannot fetch image: {err}", None

    if not url.startswith(("http://", "https://", "data:")):
        return "Unsupported image URL scheme. Only http, https, and data URLs are supported.", None

    return None, url


async def _download_image(url: str) -> tuple[bytes | None, str | None]:
    """Download image bytes from URL. Returns ``(data, error)``."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.content
            if len(data) > _MAX_IMAGE_SIZE:
                return None, f"Image exceeds {_MAX_IMAGE_SIZE // 1024 // 1024} MB size limit."
            return data, None
    except httpx.HTTPError as e:
        return None, f"Failed to download image: {e}"
    except Exception as e:
        return None, f"Error downloading image: {e}"


def _resize_image(data: bytes) -> bytes:
    """Proactively resize image to stay within model limits."""
    try:
        img = Image.open(BytesIO(data))
        w, h = img.size
        if w <= _MAX_DIMENSION and h <= _MAX_DIMENSION:
            return data
        ratio = min(_MAX_DIMENSION / w, _MAX_DIMENSION / h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format=img.format or "PNG")
        return buf.getvalue()
    except Exception:
        return data


async def _query_hf_vqa(
    image_data: bytes,
    question: str,
    model: str,
) -> str:
    """Query a Hugging Face VQA model via the free Inference API."""
    api_key = settings.huggingface_api_key
    if not api_key:
        return "Error: HUGGINGFACE_API_KEY not configured."

    url = f"{_HF_BASE}/{model}"
    headers = {"Authorization": f"Bearer {api_key}"}

    b64 = base64.b64encode(image_data).decode("utf-8")
    payload = {"inputs": {"image": b64, "question": question}}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()

        if isinstance(result, list):
            answers = [item.get("answer", "") for item in result if "answer" in item]
            return "\n".join(answers) if answers else str(result)
        if isinstance(result, dict):
            return result.get("answer", str(result))
        return str(result)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 503:
            return (
                f"Model {model} is loading on Hugging Face. "
                "Please try again in a few seconds."
            )
        return f"Image analysis failed (HTTP {e.response.status_code}): {e.response.text[:300]}"
    except Exception as e:
        return f"Image analysis failed: {e}"


@tool
async def vision_analyze(
    image_url: str,
    question: str = "Describe this image in detail.",
    model: str = DEFAULT_MODEL,
) -> str:
    """Analyze an image using a free Hugging Face vision model.

    Downloads the image, optionally resizes it, and sends it to a
    VQA model on Hugging Face Inference API.

    Args:
        image_url: URL of the image to analyze (http/https).
        question: Specific question about the image, or the analysis task.
        model: Hugging Face model ID (default: Salesforce/blip-vqa-base).
    """
    err, safe_url = _validate_image_url(image_url)
    if err:
        return err

    data, download_err = await _download_image(safe_url)
    if download_err:
        return download_err

    data = _resize_image(data)
    return await _query_hf_vqa(data, question, model)
