from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.documents.utils import sanitize_filename
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _build_s3_client():
    kwargs: dict = {
        "region_name": settings.s3_region or "auto",
        "config": Config(
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 3},
        ),
    }
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    if settings.s3_access_key_id:
        kwargs["aws_access_key_id"] = settings.s3_access_key_id
    if settings.s3_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
    return boto3.client("s3", **kwargs)


class S3StorageBackend(StorageBackend):
    """Stores files in an S3-compatible bucket.

    S3 key format: {org_id}/{uuid8}_{sanitized_filename}

    The UUID prefix prevents name collisions across uploads. The org_id
    prefix enables S3 lifecycle rules scoped to an organization.
    """

    def __init__(self) -> None:
        self.client = _build_s3_client()
        self.bucket = settings.s3_bucket_name

    async def save(
        self,
        org_id: UUID,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> str:
        object_key = f"{org_id}/{uuid.uuid4().hex[:8]}_{sanitize_filename(filename)}"
        extra_args: dict = {}
        if content_type:
            extra_args["ContentType"] = content_type
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=content,
            **extra_args,
        )
        return object_key

    async def read(self, storage_path: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=storage_path)
        return resp["Body"].read()

    async def read_stream(self, storage_path: str) -> AsyncGenerator[bytes, None]:
        resp = self.client.get_object(Bucket=self.bucket, Key=storage_path)
        for chunk in resp["Body"].iter_chunks(chunk_size=64 * 1024):
            yield chunk

    async def delete(self, storage_path: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=storage_path)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("NoSuchKey", "404", "NotFound"):
                return  # idempotent — already gone
            logger.error("Failed to delete S3 object %s: %s", storage_path, exc)
            raise

    def get_presigned_url(self, storage_path: str) -> str | None:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": storage_path},
                ExpiresIn=settings.s3_presigned_url_expiry,
            )
        except ClientError:
            logger.warning(
                "Failed to generate presigned URL for %s — falling back to proxy stream",
                storage_path,
                exc_info=True,
            )
            return None
