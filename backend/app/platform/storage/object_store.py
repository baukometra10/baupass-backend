"""
Object storage abstraction — local filesystem or S3-compatible (R2, MinIO, AWS).
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import BinaryIO


class ObjectStore:
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        raise NotImplementedError

    def get_path_or_uri(self, key: str) -> str:
        raise NotImplementedError


class LocalObjectStore(ObjectStore):
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
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
        import boto3

        self.bucket = os.getenv("S3_BUCKET", "")
        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
            aws_access_key_id=os.getenv("S3_ACCESS_KEY", ""),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY", ""),
        )

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return f"s3://{self.bucket}/{key}"

    def get_path_or_uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"


def get_object_store() -> ObjectStore:
    backend = os.getenv("UPLOAD_BACKEND", "local").strip().lower()
    if backend == "s3" and os.getenv("S3_BUCKET"):
        return S3ObjectStore()
    from backend.app.config import BaseConfig

    return LocalObjectStore(BaseConfig.LOCAL_UPLOAD_DIR)


def store_upload(file_obj: BinaryIO, *, prefix: str = "uploads", ext: str = "bin") -> str:
    key = f"{prefix}/{uuid.uuid4().hex}.{ext}"
    data = file_obj.read()
    store = get_object_store()
    store.put(key, data)
    return key
