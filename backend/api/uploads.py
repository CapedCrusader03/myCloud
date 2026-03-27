"""
Upload API routes.

All endpoints use strict Pydantic schemas for input validation
and typed response models for serialization.
"""

import os
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db, async_session
from redis_config import redis_client
from middleware import rate_limiter
from models.domain import User
from schemas import (
    InitiateUploadRequest,
    InitiateUploadResponse,
    ChunkResponse,
    UploadStatusResponse,
    ShareRequest,
    ShareResponse,
    DownloadTokenResponse,
    MessageResponse,
)
from services.auth_service import get_current_user
from services import upload_service
from services import download_service
from services import share_service
from services import file_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["Uploads"])


# ── File Listing ──────────────────────────────────────────────────────

@router.get("", response_model=list[dict])
async def list_uploads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await file_service.list_uploads(db, current_user.id)


# ── Upload Initiation ─────────────────────────────────────────────────

@router.post(
    "",
    response_model=InitiateUploadResponse,
    status_code=201,
    dependencies=[Depends(rate_limiter)],
)
async def initiate_upload(
    request: InitiateUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await upload_service.initiate_upload(
        db=db,
        user_id=current_user.id,
        filename=request.filename,
        total_size=request.total_size,
        chunk_size=request.chunk_size,
        file_checksum=request.file_checksum,
    )


# ── Chunk Upload ──────────────────────────────────────────────────────

@router.patch(
    "/{upload_id}/chunks/{chunk_index}",
    response_model=ChunkResponse,
    dependencies=[Depends(rate_limiter)],
)
async def receive_chunk(
    upload_id: str,
    chunk_index: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_data = await request.body()

    # Enforce max chunk size
    if len(raw_data) > settings.chunk_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Chunk too large. Max: {settings.chunk_size_bytes} bytes",
        )

    if len(raw_data) == 0:
        raise HTTPException(status_code=400, detail="Empty chunk body")

    res = await upload_service.process_incoming_chunk(
        db=db,
        upload_id=upload_id,
        chunk_index=chunk_index,
        raw_data=raw_data,
    )

    if res:
        return ChunkResponse(message=f"Received chunk {chunk_index} for {upload_id}")
    raise HTTPException(status_code=404, detail="Upload not found or finished")


# ── Upload Status ─────────────────────────────────────────────────────

@router.get("/{upload_id}", response_model=UploadStatusResponse)
async def get_upload_status(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    upload = await upload_service.get_upload_status(db, upload_id)
    if not upload or upload.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Upload not found")
    return await upload_service.get_upload_status_dict(upload)


@router.head("/{upload_id}")
async def resume_upload_status(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    upload = await upload_service.get_upload_status(db, upload_id)
    if not upload or upload.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Upload not found")

    res = await upload_service.get_upload_status_dict(upload)
    received_chunks = res["received_chunks"]
    headers = {
        "Upload-Offset": str(len(received_chunks) * upload.chunk_size),
        "X-Missing-Chunks": ",".join(
            str(i)
            for i in range(upload.total_chunks)
            if i not in received_chunks
        ),
    }
    return Response(headers=headers)


# ── Delete ────────────────────────────────────────────────────────────

@router.delete("/{upload_id}", response_model=MessageResponse, status_code=200)
async def delete_upload(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await file_service.delete_upload(db, upload_id, user_id=current_user.id)
    if res:
        return MessageResponse(message=f"Upload {upload_id} permanently deleted.")
    raise HTTPException(status_code=404, detail="Upload not found")


# ── SSE Progress Events ──────────────────────────────────────────────

@router.get("/{upload_id}/events")
async def stream_upload_events(upload_id: str):
    """
    Server-Sent Events endpoint for real-time upload progress.

    NOTE: EventSource cannot send Authorization headers, so this endpoint
    is NOT authenticated via Bearer token. The upload_id (a UUID known only
    to the uploader) acts as the access control.
    """
    async def event_generator():
        yield ": ok\n\n"

        # Initial sync from DB
        async with async_session() as db_session:
            upload = await upload_service.get_upload_status(db_session, upload_id)
            if upload:
                status_dict = await upload_service.get_upload_status_dict(upload)
                status_dict["event_type"] = "INITIAL_SYNC"
                status_dict["percent"] = (
                    (len(status_dict["received_chunks"]) / upload.total_chunks * 100)
                    if upload.total_chunks > 0
                    else 0
                )
                yield f"data: {json.dumps(status_dict)}\n\n"

        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"upload:{upload_id}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
        except asyncio.CancelledError:
            await pubsub.unsubscribe(f"upload:{upload_id}")
            await pubsub.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Download Token ────────────────────────────────────────────────────

@router.get("/{upload_id}/token", response_model=DownloadTokenResponse)
async def get_download_token(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    token = await download_service.generate_download_token(db, upload_id)
    if token:
        return DownloadTokenResponse(token=token)
    raise HTTPException(status_code=404, detail="Upload not found or not complete")


# ── File Download ─────────────────────────────────────────────────────

@router.get("/download/{token}")
async def download_file(token: str, db: AsyncSession = Depends(get_db)):
    upload_id = await download_service.validate_download_token(db, token)
    if not upload_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    upload = await upload_service.get_upload_status(db, str(upload_id))
    if not upload:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = f"chunks/{upload_id}_{upload.filename}"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Physical file not found on disk")

    return FileResponse(
        path=file_path,
        filename=upload.filename,
        media_type="application/octet-stream",
    )


# ── Sharing ───────────────────────────────────────────────────────────

@router.post("/{upload_id}/share", response_model=ShareResponse, status_code=201)
async def share_upload(
    upload_id: str,
    request: ShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    upload = await upload_service.get_upload_status(db, upload_id)
    if not upload or upload.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Upload not found")

    slug = await share_service.create_share_link(
        db,
        upload_id,
        ttl_hours=request.ttl_hours,
        max_downloads=request.max_downloads,
    )
    if slug:
        return ShareResponse(slug=slug, share_url=f"/s/{slug}")
    raise HTTPException(status_code=404, detail="Upload not found or not complete")
