import os
import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple
import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile, status
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging_config import logger

ALLOWED_MIME_TYPES = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg", "image/jpg"},
    "jpeg": {"image/jpeg", "image/jpg"},
    "txt": {"text/plain", "application/octet-stream"},
}


def sanitize_filename(filename: str) -> str:
    base = os.path.basename(filename or "attachment")
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return cleaned[:180] or "attachment"


def validate_upload_file(file: UploadFile, content_bytes: bytes) -> Tuple[str, str, int]:
    """Validate file extension, MIME type, and file size. Returns (safe_original_name, extension, size)."""
    original_name = sanitize_filename(file.filename or "file")
    if "." not in original_name:
        raise AppException(
            message="Uploaded file must have a valid extension (PDF, PNG, JPG, JPEG, TXT).",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_FILE_EXTENSION",
        )

    ext = original_name.rsplit(".", 1)[-1].lower()
    if ext not in settings.allowed_extensions_set:
        raise AppException(
            message=f"File extension '.{ext}' is not allowed. Allowed: {', '.join(sorted(settings.allowed_extensions_set))}.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="UNSUPPORTED_FILE_TYPE",
        )

    content_type = (file.content_type or "").lower()
    allowed_mimes = ALLOWED_MIME_TYPES.get(ext, set())
    if allowed_mimes and content_type not in allowed_mimes:
        raise AppException(
            message=f"Invalid MIME type '{content_type}' for .{ext} file.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_MIME_TYPE",
        )

    size = len(content_bytes)
    if size == 0:
        raise AppException(
            message="Uploaded file is empty.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EMPTY_FILE",
        )
    if size > settings.max_upload_size_bytes:
        raise AppException(
            message=f"File size exceeds maximum limit of {settings.MAX_UPLOAD_SIZE_MB} MB.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            error_code="FILE_TOO_LARGE",
        )

    return original_name, ext, size


class StorageProvider(ABC):
    @abstractmethod
    def save_file(self, ticket_number: str, stored_filename: str, content: bytes, content_type: str) -> str:
        """Persist file and return storage_key."""
        pass

    @abstractmethod
    def get_file_bytes(self, storage_key: str) -> bytes:
        """Read file bytes for download."""
        pass

    @abstractmethod
    def get_presigned_url(self, storage_key: str, original_filename: str) -> str | None:
        """Return pre-signed download URL if supported (S3), or None for local."""
        pass


class LocalStorageProvider(StorageProvider):
    def __init__(self, base_dir: str):
        self.base_path = Path(base_dir).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_file(self, ticket_number: str, stored_filename: str, content: bytes, content_type: str) -> str:
        ticket_dir = self.base_path / ticket_number
        ticket_dir.mkdir(parents=True, exist_ok=True)
        file_path = ticket_dir / stored_filename
        file_path.write_bytes(content)
        storage_key = f"{ticket_number}/{stored_filename}"
        logger.info(f"Stored attachment locally at {storage_key} ({len(content)} bytes)")
        return storage_key

    def get_file_bytes(self, storage_key: str) -> bytes:
        target_path = (self.base_path / storage_key).resolve()
        if not str(target_path).startswith(str(self.base_path)) or not target_path.is_file():
            raise AppException(
                message="Requested attachment file was not found on storage.",
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="ATTACHMENT_FILE_NOT_FOUND",
            )
        return target_path.read_bytes()

    def get_presigned_url(self, storage_key: str, original_filename: str) -> str | None:
        return None


class S3StorageProvider(StorageProvider):
    """Amazon S3 storage provider using IAM roles / default Boto3 credential chain."""

    def __init__(self, bucket_name: str, region: str, expiration: int = 3600):
        self.bucket_name = bucket_name
        self.region = region
        self.expiration = expiration
        self.s3_client = boto3.client("s3", region_name=region)

    def save_file(self, ticket_number: str, stored_filename: str, content: bytes, content_type: str) -> str:
        storage_key = f"TicketLogs/Tickets/{ticket_number}/Attachments/{stored_filename}"
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=content,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
            logger.info(f"Uploaded attachment to S3 s3://{self.bucket_name}/{storage_key} ({len(content)} bytes)")
            return storage_key
        except ClientError as exc:
            logger.error(f"S3 upload failed for {storage_key}: {exc}")
            raise AppException(
                message="Failed to upload attachment to S3 storage.",
                status_code=status.HTTP_502_BAD_GATEWAY,
                error_code="S3_UPLOAD_ERROR",
            )

    def get_file_bytes(self, storage_key: str) -> bytes:
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=storage_key)
            return response["Body"].read()
        except ClientError as exc:
            logger.error(f"S3 download failed for {storage_key}: {exc}")
            raise AppException(
                message="Attachment could not be retrieved from S3 storage.",
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="S3_OBJECT_NOT_FOUND",
            )

    def get_presigned_url(self, storage_key: str, original_filename: str) -> str | None:
        try:
            url = self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": storage_key,
                    "ResponseContentDisposition": f'attachment; filename="{original_filename}"',
                },
                ExpiresIn=self.expiration,
            )
            return url
        except ClientError as exc:
            logger.error(f"Failed to generate presigned URL for {storage_key}: {exc}")
            return None


def get_storage_provider() -> StorageProvider:
    if settings.STORAGE_PROVIDER.lower() == "s3":
        return S3StorageProvider(
            bucket_name=settings.S3_BUCKET_NAME,
            region=settings.AWS_REGION,
            expiration=settings.S3_PRESIGNED_URL_EXPIRATION,
        )
    return LocalStorageProvider(base_dir=settings.LOCAL_UPLOAD_DIR)


def generate_stored_filename(ext: str) -> str:
    return f"{uuid.uuid4().hex}.{ext}"
