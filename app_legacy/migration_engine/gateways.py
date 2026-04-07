"""Cloud storage gateway adapters for migration operations.

Official SDKs are imported lazily:
- AWS: boto3
- GCP: google-cloud-storage
- Azure: azure-storage-blob
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class ObjectReference:
    """Cloud object reference used by migration engine."""

    provider: str
    region: str
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"{self.provider}://{self.bucket}/{self.key}"


@dataclass(slots=True)
class ObjectMetadata:
    """Essential metadata for migration safety checks."""

    size_bytes: int
    checksum: str | None


class CloudStorageGateway(Protocol):
    """Storage gateway contract."""

    async def head(self, ref: ObjectReference) -> ObjectMetadata:
        """Read object metadata."""

    async def download(self, ref: ObjectReference, destination_path: str) -> None:
        """Download object to local path."""

    async def upload(self, source_path: str, ref: ObjectReference, storage_tier: str) -> None:
        """Upload object with target storage tier."""

    async def delete(self, ref: ObjectReference) -> None:
        """Delete object."""


class S3Gateway:
    """AWS S3 implementation."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3  # type: ignore

            self._client = boto3.client("s3")
        return self._client

    async def head(self, ref: ObjectReference) -> ObjectMetadata:
        def _head() -> ObjectMetadata:
            response = self._get_client().head_object(Bucket=ref.bucket, Key=ref.key)
            etag = str(response.get("ETag", "")).replace('"', "") or None
            return ObjectMetadata(size_bytes=int(response["ContentLength"]), checksum=etag)

        return await asyncio.to_thread(_head)

    async def download(self, ref: ObjectReference, destination_path: str) -> None:
        await asyncio.to_thread(
            self._get_client().download_file,
            ref.bucket,
            ref.key,
            destination_path,
        )

    async def upload(self, source_path: str, ref: ObjectReference, storage_tier: str) -> None:
        await asyncio.to_thread(
            self._get_client().upload_file,
            source_path,
            ref.bucket,
            ref.key,
            ExtraArgs={"StorageClass": storage_tier},
        )

    async def delete(self, ref: ObjectReference) -> None:
        await asyncio.to_thread(self._get_client().delete_object, Bucket=ref.bucket, Key=ref.key)


class GCSGateway:
    """Google Cloud Storage implementation."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import storage  # type: ignore

            self._client = storage.Client()
        return self._client

    async def head(self, ref: ObjectReference) -> ObjectMetadata:
        def _head() -> ObjectMetadata:
            bucket = self._get_client().bucket(ref.bucket)
            blob = bucket.blob(ref.key)
            blob.reload()
            checksum = blob.md5_hash
            return ObjectMetadata(size_bytes=int(blob.size or 0), checksum=checksum)

        return await asyncio.to_thread(_head)

    async def download(self, ref: ObjectReference, destination_path: str) -> None:
        def _download() -> None:
            bucket = self._get_client().bucket(ref.bucket)
            blob = bucket.blob(ref.key)
            blob.download_to_filename(destination_path)

        await asyncio.to_thread(_download)

    async def upload(self, source_path: str, ref: ObjectReference, storage_tier: str) -> None:
        def _upload() -> None:
            bucket = self._get_client().bucket(ref.bucket)
            blob = bucket.blob(ref.key)
            blob.storage_class = storage_tier
            blob.upload_from_filename(source_path)

        await asyncio.to_thread(_upload)

    async def delete(self, ref: ObjectReference) -> None:
        def _delete() -> None:
            bucket = self._get_client().bucket(ref.bucket)
            blob = bucket.blob(ref.key)
            blob.delete()

        await asyncio.to_thread(_delete)


class AzureBlobGateway:
    """Azure Blob Storage implementation."""

    def __init__(self, connection_string: str | None = None) -> None:
        self._connection_string = connection_string
        self._service = None

    def _get_service(self):
        if self._service is None:
            from azure.storage.blob import BlobServiceClient  # type: ignore

            if self._connection_string:
                self._service = BlobServiceClient.from_connection_string(self._connection_string)
            else:
                raise RuntimeError("Azure connection string is required for AzureBlobGateway")
        return self._service

    async def head(self, ref: ObjectReference) -> ObjectMetadata:
        def _head() -> ObjectMetadata:
            blob = self._get_service().get_blob_client(container=ref.bucket, blob=ref.key)
            props = blob.get_blob_properties()
            md5 = None
            if props.content_settings and props.content_settings.content_md5:
                md5 = base64.b64encode(props.content_settings.content_md5).decode("ascii")
            return ObjectMetadata(size_bytes=int(props.size), checksum=md5)

        return await asyncio.to_thread(_head)

    async def download(self, ref: ObjectReference, destination_path: str) -> None:
        def _download() -> None:
            blob = self._get_service().get_blob_client(container=ref.bucket, blob=ref.key)
            with open(destination_path, "wb") as handle:
                stream = blob.download_blob()
                handle.write(stream.readall())

        await asyncio.to_thread(_download)

    async def upload(self, source_path: str, ref: ObjectReference, storage_tier: str) -> None:
        def _upload() -> None:
            blob = self._get_service().get_blob_client(container=ref.bucket, blob=ref.key)
            with open(source_path, "rb") as handle:
                blob.upload_blob(handle, overwrite=True, standard_blob_tier=storage_tier)

        await asyncio.to_thread(_upload)

    async def delete(self, ref: ObjectReference) -> None:
        def _delete() -> None:
            blob = self._get_service().get_blob_client(container=ref.bucket, blob=ref.key)
            blob.delete_blob()

        await asyncio.to_thread(_delete)


class GatewayFactory:
    """Builds provider-specific gateways."""

    def __init__(self, azure_connection_string: str | None = None):
        self._azure_connection_string = azure_connection_string

    def get_gateway(self, provider: str) -> CloudStorageGateway:
        normalized = provider.lower()
        if normalized == "aws":
            return S3Gateway()
        if normalized == "gcp":
            return GCSGateway()
        if normalized == "azure":
            return AzureBlobGateway(connection_string=self._azure_connection_string)
        raise KeyError(f"Unsupported provider: {provider}")
