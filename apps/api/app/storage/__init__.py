from __future__ import annotations

from app.core.config import settings
from app.storage.base import StorageBackend

_local_backend: StorageBackend | None = None
_s3_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return the currently configured storage backend (singleton per process)."""
    match settings.storage_backend:
        case "local":
            return get_local_backend()
        case "s3":
            return get_s3_backend()
        case _:
            raise ValueError(
                f"Unknown storage_backend: {settings.storage_backend!r}. "
                f"Expected 'local' or 's3'."
            )


def get_local_backend() -> StorageBackend:
    global _local_backend
    if _local_backend is None:
        from app.storage.local import LocalStorageBackend

        _local_backend = LocalStorageBackend()
    return _local_backend


def get_s3_backend() -> StorageBackend:
    global _s3_backend
    if _s3_backend is None:
        from app.storage.s3 import S3StorageBackend

        _s3_backend = S3StorageBackend()
    return _s3_backend
