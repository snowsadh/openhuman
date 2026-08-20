"""Image generation tool for AI employees.

Generates images using a free Hugging Face Inference API model
(FLUX.1-schnell by default). Requires ``HUGGINGFACE_API_KEY``
to be set in the environment.
"""

from __future__ import annotations

import logging

import httpx
from langchain_core.tools import tool

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"
DEFAULT_SIZE = "1024x1024"
_HF_BASE = "https://api-inference.huggingface.co/models"


@tool
def generate_image(
    prompt: str,
    size: str = DEFAULT_SIZE,
    model: str = DEFAULT_MODEL,
) -> str:
    """Generate an image from a text description using a free HF model.

    Args:
        prompt: Detailed description of the image to generate.
        size: Ignored by the HF free API (model default used). Kept for
              compatibility with existing callers.
        model: Hugging Face model ID (default: black-forest-labs/FLUX.1-schnell).
    """
    api_key = settings.huggingface_api_key
    if not api_key:
        return (
            "Error: HUGGINGFACE_API_KEY not configured. "
            "Get a free token at https://huggingface.co/settings/tokens"
        )

    url = f"{_HF_BASE}/{model}"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, headers=headers, json={"inputs": prompt})
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "image" in content_type:
                import tempfile

                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.write(resp.content)
                tmp.close()
                return f"Generated image saved to: {tmp.name}"
            else:
                detail = resp.text[:500]
                return f"Image generation failed: unexpected response — {detail}"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 503:
            return (
                f"Model {model} is loading on Hugging Face. "
                "Please try again in a few seconds."
            )
        return f"Image generation failed (HTTP {e.response.status_code}): {e.response.text[:300]}"
    except Exception as e:
        logger.exception("Image generation failed")
        return f"Image generation failed: {e}"
