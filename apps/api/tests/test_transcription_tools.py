"""Tests for transcription_tools module."""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import httpx


class TestTranscribeAudio:
    def test_no_api_key(self):
        from app.agent.tools.transcription_tools import transcribe_audio

        with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
            with patch("app.agent.tools.transcription_tools.settings") as mock_settings:
                mock_settings.huggingface_api_key = ""
                result = transcribe_audio.invoke({"file_path": tmp.name})
                assert "not configured" in result.lower()

    def test_successful_transcription(self):
        from app.agent.tools.transcription_tools import transcribe_audio

        with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
            with (
                patch("app.agent.tools.transcription_tools.settings") as mock_settings,
                patch("httpx.Client") as mock_client_cls,
            ):
                mock_settings.huggingface_api_key = "hf-test"
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"text": "Hello world"}
                mock_resp.raise_for_status = MagicMock()
                mock_context = MagicMock()
                mock_client = MagicMock()
                mock_client.post.return_value = mock_resp
                mock_context.__enter__.return_value = mock_client
                mock_client_cls.return_value = mock_context

                result = transcribe_audio.invoke({"file_path": tmp.name})
                assert "Hello world" in result

    def test_api_error_handled(self):
        from app.agent.tools.transcription_tools import transcribe_audio

        with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
            with (
                patch("app.agent.tools.transcription_tools.settings") as mock_settings,
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

                result = transcribe_audio.invoke({"file_path": tmp.name})
                assert "failed" in result.lower()

    def test_unsupported_format(self):
        from app.agent.tools.transcription_tools import transcribe_audio

        with tempfile.NamedTemporaryFile(suffix=".wma") as tmp:
            result = transcribe_audio.invoke({"file_path": tmp.name})
            assert "unsupported" in result.lower()

    def test_file_not_found(self):
        from app.agent.tools.transcription_tools import transcribe_audio

        result = transcribe_audio.invoke({"file_path": "/nonexistent/path.mp3"})
        assert "not found" in result.lower()
