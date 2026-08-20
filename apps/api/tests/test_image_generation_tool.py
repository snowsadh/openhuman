"""Tests for image_generation_tool module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx


class TestGenerateImage:
    def test_no_api_key(self):
        from app.agent.tools.image_generation_tool import generate_image

        with patch("app.agent.tools.image_generation_tool.settings") as mock_settings:
            mock_settings.huggingface_api_key = ""
            result = generate_image.invoke({"prompt": "a cat"})
            assert "not configured" in result.lower()

    def test_successful_generation(self):
        from app.agent.tools.image_generation_tool import generate_image

        with (
            patch("app.agent.tools.image_generation_tool.settings") as mock_settings,
            patch("httpx.Client") as mock_client_cls,
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            mock_settings.huggingface_api_key = "hf-test"
            mock_resp = MagicMock()
            mock_resp.headers = {"content-type": "image/png"}
            mock_resp.content = b"fake-png-bytes"
            mock_resp.raise_for_status = MagicMock()
            mock_context = MagicMock()
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_context.__enter__.return_value = mock_client
            mock_client_cls.return_value = mock_context
            mock_tmp.return_value.name = "/tmp/abc.png"

            result = generate_image.invoke({"prompt": "a cat"})
            assert "saved to" in result
            assert "/tmp/abc.png" in result

    def test_api_error_handled(self):
        from app.agent.tools.image_generation_tool import generate_image

        with (
            patch("app.agent.tools.image_generation_tool.settings") as mock_settings,
            patch("httpx.Client") as mock_client_cls,
        ):
            mock_settings.huggingface_api_key = "hf-test"
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal error"
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=mock_resp
            )
            mock_context = MagicMock()
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_context.__enter__.return_value = mock_client
            mock_client_cls.return_value = mock_context

            result = generate_image.invoke({"prompt": "a cat"})
            assert "failed" in result.lower()
