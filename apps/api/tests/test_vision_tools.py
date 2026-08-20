"""Tests for vision_tools module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_no_api_key():
    from app.agent.tools.vision_tools import vision_analyze

    with (
        patch("app.agent.tools.vision_tools.settings") as mock_settings,
        patch(
            "app.agent.tools.vision_tools._download_image",
            return_value=(b"fake-img", None),
        ),
        patch(
            "app.agent.tools.vision_tools._resize_image",
            return_value=b"fake-img",
        ),
    ):
        mock_settings.huggingface_api_key = ""
        result = await vision_analyze.ainvoke({
            "image_url": "https://example.com/img.png",
        })
        assert "not configured" in result.lower()


@pytest.mark.asyncio
async def test_download_failure():
    from app.agent.tools.vision_tools import vision_analyze

    with (
        patch("app.agent.tools.vision_tools.settings") as mock_settings,
        patch(
            "app.agent.tools.vision_tools._download_image",
            return_value=(None, "Download error"),
        ),
    ):
        mock_settings.huggingface_api_key = "hf-test"
        result = await vision_analyze.ainvoke({
            "image_url": "https://example.com/img.png",
        })
        assert "download" in result.lower()


@pytest.mark.asyncio
async def test_successful_analysis():
    from app.agent.tools.vision_tools import vision_analyze

    with (
        patch("app.agent.tools.vision_tools.settings") as mock_settings,
        patch(
            "app.agent.tools.vision_tools._download_image",
            return_value=(b"fake-img", None),
        ),
        patch(
            "app.agent.tools.vision_tools._resize_image",
            return_value=b"fake-img",
        ),
        patch(
            "app.agent.tools.vision_tools._query_hf_vqa",
            new=AsyncMock(return_value="A cat"),
        ),
    ):
        mock_settings.huggingface_api_key = "hf-test"
        result = await vision_analyze.ainvoke({
            "image_url": "https://example.com/img.png",
        })
        assert "A cat" in result


@pytest.mark.asyncio
async def test_ssrf_blocked():
    from app.agent.tools.vision_tools import vision_analyze

    result = await vision_analyze.ainvoke({
        "image_url": "http://169.254.169.254/latest/meta-data/",
    })
    assert "cannot fetch" in result.lower()


@pytest.mark.asyncio
async def test_invalid_scheme():
    from app.agent.tools.vision_tools import vision_analyze

    result = await vision_analyze.ainvoke({
        "image_url": "ftp://example.com/img.png",
    })
    assert "blocked scheme" in result.lower()


@pytest.mark.asyncio
async def test_query_hf_vqa_success():
    from app.agent.tools.vision_tools import _query_hf_vqa

    with (
        patch("app.agent.tools.vision_tools.settings") as mock_settings,
        patch("httpx.AsyncClient") as mock_cls,
    ):
        mock_settings.huggingface_api_key = "hf-test"
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"answer": "a dog"}]
        mock_resp.raise_for_status = MagicMock()
        mock_context = AsyncMock()
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_context.__aenter__.return_value = mock_client
        mock_cls.return_value = mock_context

        result = await _query_hf_vqa(b"img-data", "What is this?", "test/model")
        assert "a dog" in result
