import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aioboto3

from app.core.config import get_settings

settings = get_settings()

_DEFAULT_MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024


@dataclass(slots=True)
class S3Object:
    bucket: str
    key: str
    body: bytes
    content_type: str | None = None
    metadata: dict[str, str] | None = None
    etag: str | None = None
    version_id: str | None = None


@dataclass(slots=True)
class S3UploadResult:
    bucket: str
    key: str
    etag: str | None = None
    version_id: str | None = None
    location: str | None = None


class AsyncS3Client:
    def __init__(
        self,
        *,
        region_name: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self._region_name = region_name or settings.AWS_REGION
        self._endpoint_url = endpoint_url
        self._session = aioboto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=self._region_name,
        )

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self._region_name:
            kwargs["region_name"] = self._region_name
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        return kwargs

    def client(self):
        return self._session.client("s3", **self._client_kwargs())

    async def get_object(self, *, bucket: str, key: str) -> S3Object:
        async with self.client() as s3_client:
            response = await s3_client.get_object(Bucket=bucket, Key=key)
            async with response["Body"] as stream:
                body = await stream.read()

        return S3Object(
            bucket=bucket,
            key=key,
            body=body,
            content_type=response.get("ContentType"),
            metadata=response.get("Metadata"),
            etag=response.get("ETag"),
            version_id=response.get("VersionId"),
        )

    async def put_object(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes | bytearray | memoryview | str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> S3UploadResult:
        payload = body.encode("utf-8") if isinstance(body, str) else body
        params: dict[str, Any] = {"Bucket": bucket, "Key": key, "Body": payload}
        if content_type:
            params["ContentType"] = content_type
        if metadata:
            params["Metadata"] = metadata

        async with self.client() as s3_client:
            response = await s3_client.put_object(**params)

        return S3UploadResult(
            bucket=bucket,
            key=key,
            etag=response.get("ETag"),
            version_id=response.get("VersionId"),
            location=f"s3://{bucket}/{key}",
        )

    async def generate_presigned_url(
        self,
        *,
        bucket: str,
        key: str,
        operation: str = "get_object",
        expires_in: int = 3600,
        extra_params: dict[str, Any] | None = None,
        http_method: str | None = None,
    ) -> str:
        params = {"Bucket": bucket, "Key": key}
        if extra_params:
            params.update(extra_params)

        async with self.client() as s3_client:
            return await asyncio.to_thread(
                s3_client.generate_presigned_url,
                operation,
                Params=params,
                ExpiresIn=expires_in,
                HttpMethod=http_method,
            )

    async def upload_file(
        self,
        *,
        bucket: str,
        key: str,
        file_path: str | Path,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> S3UploadResult:
        path = Path(file_path)
        body = await asyncio.to_thread(path.read_bytes)
        return await self.put_object(
            bucket=bucket,
            key=key,
            body=body,
            content_type=content_type,
            metadata=metadata,
        )

    async def multipart_upload(
        self,
        *,
        bucket: str,
        key: str,
        file_path: str | Path,
        chunk_size: int = _DEFAULT_MULTIPART_CHUNK_SIZE,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> S3UploadResult:
        if chunk_size < 5 * 1024 * 1024:
            raise ValueError("chunk_size must be at least 5 MB for multipart uploads.")

        path = Path(file_path)
        upload_id: str | None = None
        parts: list[dict[str, Any]] = []

        async with self.client() as s3_client:
            create_params: dict[str, Any] = {"Bucket": bucket, "Key": key}
            if content_type:
                create_params["ContentType"] = content_type
            if metadata:
                create_params["Metadata"] = metadata

            try:
                response = await s3_client.create_multipart_upload(**create_params)
                upload_id = response["UploadId"]

                with path.open("rb") as file_obj:
                    part_number = 1
                    while True:
                        chunk = await asyncio.to_thread(file_obj.read, chunk_size)
                        if not chunk:
                            break

                        part_response = await s3_client.upload_part(
                            Bucket=bucket,
                            Key=key,
                            UploadId=upload_id,
                            PartNumber=part_number,
                            Body=chunk,
                        )
                        parts.append({"PartNumber": part_number, "ETag": part_response["ETag"]})
                        part_number += 1

                complete_response = await s3_client.complete_multipart_upload(
                    Bucket=bucket,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
            except Exception:
                if upload_id:
                    await s3_client.abort_multipart_upload(
                        Bucket=bucket,
                        Key=key,
                        UploadId=upload_id,
                    )
                raise

        return S3UploadResult(
            bucket=bucket,
            key=key,
            etag=complete_response.get("ETag"),
            version_id=complete_response.get("VersionId"),
            location=complete_response.get("Location", f"s3://{bucket}/{key}"),
        )


async def get_s3_object(*, bucket: str, key: str) -> S3Object:
    return await AsyncS3Client().get_object(bucket=bucket, key=key)


async def put_s3_object(
    *,
    bucket: str,
    key: str,
    body: bytes | bytearray | memoryview | str,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> S3UploadResult:
    return await AsyncS3Client().put_object(
        bucket=bucket,
        key=key,
        body=body,
        content_type=content_type,
        metadata=metadata,
    )


async def generate_s3_presigned_url(
    *,
    bucket: str,
    key: str,
    operation: str = "get_object",
    expires_in: int = 3600,
    extra_params: dict[str, Any] | None = None,
    http_method: str | None = None,
) -> str:
    return await AsyncS3Client().generate_presigned_url(
        bucket=bucket,
        key=key,
        operation=operation,
        expires_in=expires_in,
        extra_params=extra_params,
        http_method=http_method,
    )


async def upload_s3_file(
    *,
    bucket: str,
    key: str,
    file_path: str | Path,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> S3UploadResult:
    return await AsyncS3Client().upload_file(
        bucket=bucket,
        key=key,
        file_path=file_path,
        content_type=content_type,
        metadata=metadata,
    )


async def multipart_upload_s3_file(
    *,
    bucket: str,
    key: str,
    file_path: str | Path,
    chunk_size: int = _DEFAULT_MULTIPART_CHUNK_SIZE,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> S3UploadResult:
    return await AsyncS3Client().multipart_upload(
        bucket=bucket,
        key=key,
        file_path=file_path,
        chunk_size=chunk_size,
        content_type=content_type,
        metadata=metadata,
    )


__all__ = [
    "AsyncS3Client",
    "S3Object",
    "S3UploadResult",
    "generate_s3_presigned_url",
    "get_s3_object",
    "multipart_upload_s3_file",
    "put_s3_object",
    "upload_s3_file",
]
