from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.documents.utils import sanitize_filename
from app.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Stores files under settings.upload_dir / {org_id} / {uuid8}_{safe_filename}.

    The UUID prefix prevents name collisions — mirroring the S3 backend pattern.
    """

    @staticmethod
    def _upload_root() -> Path:
        return Path(settings.upload_dir)

    async def save(
        self,
        org_id: UUID,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> str:
        safe_name = sanitize_filename(filename)
        prefix = uuid.uuid4().hex[:8]
        org_dir = self._upload_root() / str(org_id)
        org_dir.mkdir(parents=True, exist_ok=True)
        dest = org_dir / f"{prefix}_{safe_name}"
        dest.write_bytes(content)
        return str(dest)

    async def read(self, storage_path: str) -> bytes:
        return Path(storage_path).read_bytes()

    async def read_stream(self, storage_path: str) -> AsyncGenerator[bytes, None]:
        with Path(storage_path).open("rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    async def delete(self, storage_path: str) -> None:
        path = Path(storage_path)
        if path.exists():
            path.unlink(missing_ok=True)
