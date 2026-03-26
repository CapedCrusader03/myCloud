import uuid
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from models.domain import Upload, Chunk
import hashlib
import json
from services import storage_service
from redis_config import redis_client

logger = logging.getLogger(__name__)

async def broadcast_upload_event(upload: Upload, event_type: str, extra: dict = None):
    """Centralized helper to broadcast SSE events via Redis"""
    payload = {
        "upload_id": str(upload.id),
        "status": upload.status,
        "event_type": event_type,
        "total_chunks": upload.total_chunks,
        "percent": 0.0,
    }
    
    # Calculate progress if applicable
    if upload.total_chunks > 0:
        # Note: In a high-perf scenario, we might pass the 'uploaded_count' 
        # to avoid a DB query here, but for clarity we'll use the upload object if available.
        pass

    if extra:
        payload.update(extra)
        
    await redis_client.publish(f"upload:{upload.id}", json.dumps(payload))

async def initiate_upload(
    db: AsyncSession, 
    filename: str, 
    total_size: int, 
    chunk_size: int, 
    file_checksum: str
):
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
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )

    db.add(new_upload)
    await db.commit()
    await db.refresh(new_upload)
    return {"upload_id": str(new_upload.id)}

async def process_incoming_chunk(
    db: AsyncSession,
    upload_id: str,
    chunk_index: int,
    raw_data: bytes
):
    # 1. Fetch upload with a ROW LOCK (SELECT FOR UPDATE)
    # This ensures that if 10 chunks arrive at once, they wait their turn
    # to update the database and check the total count.
    stmt_upload = select(Upload).where(Upload.id == uuid.UUID(upload_id)).with_for_update()
    result = await db.execute(stmt_upload)
    upload = result.scalar_one_or_none()
    
    if not upload:
        return False
        
    # Guard: If the upload is already finished or cancelled, don't accept more chunks
    if upload.status in ["complete", "cancelled"]:
        return False
        
    # Idempotency: If the client accidentally sends Chunk 4 twice, ignore the second one!
    stmt_check = select(Chunk).where(
        Chunk.upload_id == upload.id,
        Chunk.chunk_index == chunk_index,
        Chunk.is_uploaded == True
    )
    if await db.scalar(stmt_check):
        return True # Chunk already saved, exit early without touching the disk!
        
    size = len(raw_data)
    checksum = hashlib.sha256(raw_data).hexdigest()
    
    # 2. Write the bytes to the hard drive!
    await storage_service.write_chunk(str(upload_id), chunk_index, raw_data)

    # 3. Save the record to the database
    upload_chunk = Chunk(
        upload_id=upload.id,
        chunk_index=chunk_index,
        size=size,
        checksum=checksum,
        is_uploaded=True,
    )
    db.add(upload_chunk)
    await db.commit()
    
    # Check if ALL chunks have been fully received
    stmt = select(func.count()).where(Chunk.upload_id == upload.id, Chunk.is_uploaded == True)
    uploaded_count = await db.scalar(stmt)
    
    percent = (uploaded_count / upload.total_chunks) * 100
    
    # BROADCAST PROGRESS
    await broadcast_upload_event(upload, "CHUNK_RECEIVED", {
        "received_chunks": uploaded_count,
        "percent": percent
    })
    
    if uploaded_count == upload.total_chunks and upload.status == "uploading":
        upload.status = "assembling"
        await db.commit()
        
        # BROADCAST ASSEMBLY START
        await broadcast_upload_event(upload, "ASSEMBLY_STARTED", {
            "received_chunks": uploaded_count,
            "percent": 100.0
        })
        
        try:
            # 3. Trigger assembly and check for corruption
            actual_checksum = await storage_service.assemble_file(
                upload_id=str(upload.id),
                total_chunks=upload.total_chunks,
                final_filename=upload.filename
            )
            
            if actual_checksum == upload.file_checksum:
                upload.status = "complete"
                event_type = "UPLOAD_COMPLETE"
            else:
                upload.status = "error"
                event_type = "UPLOAD_ERROR"
        except Exception as e:
            logger.error(f"Assembly failed for {upload.id}: {e}")
            upload.status = "error"
            event_type = "UPLOAD_ERROR"
            
        await db.commit()
        
        # BROADCAST FINAL RESULT
        await broadcast_upload_event(upload, event_type, {
            "received_chunks": uploaded_count,
            "percent": 100.0
        })
        
    return True

async def get_upload_status(db: AsyncSession, upload_id: str):
    try:
        uid = uuid.UUID(upload_id)
    except ValueError:
        return None
        
    # Eagerly load the related chunks so we can list their indexes
    stmt = select(Upload).options(selectinload(Upload.chunks)).where(Upload.id == uid)
    result = await db.execute(stmt)
    upload = result.scalar_one_or_none()
    
    if not upload:
        return None
        
    received_indexes = [c.chunk_index for c in upload.chunks if c.is_uploaded]
    
    return {
        "upload_id": str(upload.id),
        "filename": upload.filename,
        "status": upload.status,
        "total_chunks": upload.total_chunks,
        "received_chunks": sorted(received_indexes)
    }

async def cancel_upload(db: AsyncSession, upload_id: str):
    try:
        uid = uuid.UUID(upload_id)
    except ValueError:
        return False
        
    upload = await db.get(Upload, uid)
    if not upload:
        return False
        
    # Delete the temporary binary chunk files from the physical hard drive
    await storage_service.delete_chunks(upload_id)
    
    # Mark as cancelled so users can't PATCH to it anymore
    upload.status = "cancelled"
    await db.commit()
    
    # BROADCAST CANCELLATION
    await broadcast_upload_event(upload, "UPLOAD_CANCELLED")
    
    return True
