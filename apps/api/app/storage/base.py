from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from uuid import UUID


class StorageBackend(ABC):
    """Abstract interface for pluggable file storage backends."""

    @abstractmethod
    async def save(
        self,
        org_id: UUID,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> str:
        """Persist file content and return a storage_path for the DB record."""
        ...

    @abstractmethod
    async def read(self, storage_path: str) -> bytes:
        """Read entire file content as bytes."""
        ...

    @abstractmethod
    async def read_stream(self, storage_path: str) -> AsyncGenerator[bytes, None]:
        """Stream file content in chunks (for download responses)."""
        ...

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        """Remove file from storage. Must be idempotent (no error if missing)."""
        ...

    def get_presigned_url(self, storage_path: str) -> str | None:
        """Return a presigned download URL, or None if not supported.

        When a backend returns a URL the router can 302-redirect clients
        instead of proxying the bytes through the API server."""
        return None
