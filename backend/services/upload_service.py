"""
Upload orchestration service.

Handles upload initiation, chunk processing, and assembly.
Download tokens, share links, and file management are in their
respective services (download_service, share_service, file_service).
"""

import uuid
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from fastapi import HTTPException

from config import settings
from models.domain import Upload, Chunk
from services import storage_service
from redis_config import redis_client

logger = logging.getLogger(__name__)


# ── SSE Broadcasting ──────────────────────────────────────────────────

async def broadcast_upload_event(
    upload: Upload, event_type: str, extra: dict | None = None
) -> None:
    """Publish an SSE event to the Redis channel for this upload."""
    payload = {
        "upload_id": str(upload.id),
        "status": upload.status,
        "event_type": event_type,
        "total_chunks": upload.total_chunks,
        "percent": 0.0,
    }
    if extra:
        payload.update(extra)

    await redis_client.publish(f"upload:{upload.id}", json.dumps(payload))


# ── Upload Initiation ─────────────────────────────────────────────────

async def get_total_storage_used(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Sum total_size of all non-deleted uploads for a user."""
    stmt = select(func.sum(Upload.total_size)).where(Upload.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar() or 0


async def initiate_upload(
    db: AsyncSession,
    user_id: uuid.UUID,
    filename: str,
    total_size: int,
    chunk_size: int,
    file_checksum: str,
) -> dict:
    """Create a new upload record after validating the storage quota."""
    current_storage = await get_total_storage_used(db, user_id)

    if current_storage + total_size > settings.max_storage_bytes:
        remaining = (settings.max_storage_bytes - current_storage) / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Storage limit exceeded. Remaining space: {remaining:.2f} MB",
        )

    upload_id = uuid.uuid4()
    total_chunks = (total_size + chunk_size - 1) // chunk_size

    new_upload = Upload(
        id=upload_id,
        filename=filename,
        total_size=total_size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        file_checksum=file_checksum,
        status="uploading",
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )

    db.add(new_upload)
    await db.commit()
    await db.refresh(new_upload)
    return {"upload_id": str(new_upload.id)}


# ── Chunk Processing ──────────────────────────────────────────────────

async def process_incoming_chunk(
    db: AsyncSession,
    upload_id: str,
    chunk_index: int,
    raw_data: bytes,
) -> bool:
    """
    Process a single chunk: validate, write to storage, update DB.
    Returns True on success, False if the upload doesn't exist or is finished.
    """
    # Row lock to serialize concurrent chunk writes for the same upload
    stmt_upload = (
        select(Upload)
        .where(Upload.id == uuid.UUID(upload_id))
        .with_for_update()
    )
    result = await db.execute(stmt_upload)
    upload = result.scalar_one_or_none()

    if not upload:
        return False

    if upload.status in ("complete", "cancelled"):
        return False

    # Idempotency: skip if chunk already exists
    stmt_check = select(Chunk).where(
        Chunk.upload_id == upload.id,
        Chunk.chunk_index == chunk_index,
        Chunk.is_uploaded == True,
    )
    if await db.scalar(stmt_check):
        return True

    size = len(raw_data)
    checksum = hashlib.sha256(raw_data).hexdigest()

    # Write bytes to storage
    await storage_service.write_chunk(str(upload_id), chunk_index, raw_data)

    # Record in database
    upload_chunk = Chunk(
        upload_id=upload.id,
        chunk_index=chunk_index,
        size=size,
        checksum=checksum,
        is_uploaded=True,
    )
    db.add(upload_chunk)
    await db.commit()

    # Count progress
    stmt_count = select(func.count()).where(
        Chunk.upload_id == upload.id, Chunk.is_uploaded == True
    )
    uploaded_count = await db.scalar(stmt_count)
    percent = (uploaded_count / upload.total_chunks) * 100

    await broadcast_upload_event(
        upload, "CHUNK_RECEIVED", {"received_chunks": uploaded_count, "percent": percent}
    )

    # Check completion
    if uploaded_count == upload.total_chunks and upload.status == "uploading":
        upload.status = "assembling"
        await db.commit()

        await broadcast_upload_event(
            upload,
            "ASSEMBLY_STARTED",
            {"received_chunks": uploaded_count, "percent": 100.0},
        )

        try:
            actual_checksum = await storage_service.assemble_file(
                upload_id=str(upload.id),
                total_chunks=upload.total_chunks,
                final_filename=upload.filename,
            )

            if actual_checksum == upload.file_checksum:
                upload.status = "complete"
                event_type = "UPLOAD_COMPLETE"
            else:
                upload.status = "error"
                event_type = "UPLOAD_ERROR"
        except Exception as e:
            logger.error("Assembly failed for %s: %s", upload.id, e)
            upload.status = "error"
            event_type = "UPLOAD_ERROR"

        await db.commit()

        await broadcast_upload_event(
            upload, event_type, {"received_chunks": uploaded_count, "percent": 100.0}
        )

    return True


# ── Upload Status & Control ───────────────────────────────────────────

async def get_upload_status(db: AsyncSession, upload_id: str) -> Upload | None:
    """Fetch an upload with its chunks eagerly loaded."""
    try:
        uid = uuid.UUID(upload_id)
    except ValueError:
        return None

    stmt = select(Upload).options(selectinload(Upload.chunks)).where(Upload.id == uid)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_upload_status_dict(upload: Upload) -> dict:
    """Serialize upload status to a dict."""
    received_indexes = [c.chunk_index for c in upload.chunks if c.is_uploaded]
    return {
        "upload_id": str(upload.id),
        "filename": upload.filename,
        "status": upload.status,
        "total_chunks": upload.total_chunks,
        "received_chunks": sorted(received_indexes),
    }


async def cancel_upload(db: AsyncSession, upload_id: str) -> bool:
    """Cancel an upload and delete its temporary chunk files."""
    try:
        uid = uuid.UUID(upload_id)
    except ValueError:
        return False

    upload = await db.get(Upload, uid)
    if not upload:
        return False

    await storage_service.delete_chunks(upload_id)

    upload.status = "cancelled"
    await db.commit()

    await broadcast_upload_event(upload, "UPLOAD_CANCELLED")
    return True
