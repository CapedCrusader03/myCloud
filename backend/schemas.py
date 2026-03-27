"""
Pydantic request/response schemas.

Strict validation contracts for all API endpoints.
Using these as response_model on endpoints gives us automatic
serialization, documentation, and type safety.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
import re


# ── Auth ──────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Uploads ───────────────────────────────────────────────────────────

class InitiateUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    total_size: int = Field(gt=0, le=5 * 1024 * 1024 * 1024)  # max 5GB
    chunk_size: int = Field(gt=0, le=10 * 1024 * 1024)  # max 10MB
    file_checksum: str = Field(min_length=64, max_length=64)

    @field_validator("file_checksum")
    @classmethod
    def validate_checksum_hex(cls, v: str) -> str:
        if not re.match(r"^[0-9a-f]{64}$", v):
            raise ValueError("file_checksum must be a 64-character lowercase hex SHA-256 hash")
        return v

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        # Prevent path traversal
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("filename must not contain path separators or '..'")
        return v


class InitiateUploadResponse(BaseModel):
    upload_id: str


class ChunkResponse(BaseModel):
    message: str


class UploadStatusResponse(BaseModel):
    upload_id: str
    filename: str
    status: str
    total_chunks: int
    received_chunks: list[int]


class FileListItem(BaseModel):
    upload_id: str
    filename: str
    total_size: int
    created_at: str
    status: str


# ── Sharing ───────────────────────────────────────────────────────────

class ShareRequest(BaseModel):
    ttl_hours: int = Field(default=24, ge=1, le=720)  # max 30 days
    max_downloads: Optional[int] = Field(default=None, ge=1, le=10000)


class ShareResponse(BaseModel):
    slug: str
    share_url: str


class DownloadTokenResponse(BaseModel):
    token: str


# ── Generic ───────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
