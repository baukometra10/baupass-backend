"""
Object storage abstraction — local filesystem or S3-compatible (R2, MinIO, AWS).
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
import logging
from typing import BinaryIO

logger = logging.getLogger(__name__)


class ObjectStore:
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        raise NotImplementedError

    def get_path_or_uri(self, key: str) -> str:
        raise NotImplementedError


class LocalObjectStore(ObjectStore):
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def get_path_or_uri(self, key: str) -> str:
        return str(self.base_dir / key)


class S3ObjectStore(ObjectStore):
    def __init__(self):
        try:
            import boto3
        except ImportError:
            logger.error("The 'boto3' library is required for S3 storage but was not found.")
            raise RuntimeError("Missing dependency: boto3. Install it with 'pip install boto3'.")
            
        self.bucket = os.getenv("S3_BUCKET", "")
        if not self.bucket:
            logger.error("S3_BUCKET environment variable is not set.")
            raise ValueError("S3_BUCKET is required for S3ObjectStore configuration.")

        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
            aws_access_key_id=os.getenv("S3_ACCESS_KEY") or None,
            aws_secret_access_key=os.getenv("S3_SECRET_KEY") or None,
            region_name=os.getenv("S3_REGION") or None,
        )

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        except Exception as e:
            logger.error(f"S3 Upload failed for key {key}: {str(e)}")
            raise
        return f"s3://{self.bucket}/{key}"

    def get_path_or_uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"


def get_object_store() -> ObjectStore:
    backend = os.getenv("UPLOAD_BACKEND", "local").strip().lower()
    if backend == "s3":
        if os.getenv("S3_BUCKET"):
            return S3ObjectStore()
        else:
            logger.warning("UPLOAD_BACKEND set to 's3' but S3_BUCKET is missing. Falling back to 'local'.")

    # Lazy import to avoid circular dependency with config
    from backend.app.config import BaseConfig
    return LocalObjectStore(BaseConfig.LOCAL_UPLOAD_DIR)


def store_upload(file_obj: BinaryIO, *, prefix: str = "uploads", ext: str = "bin") -> str:
    key = f"{prefix}/{uuid.uuid4().hex}.{ext}"
    data = file_obj.read()
    store = get_object_store()
    store.put(key, data)
    return key
