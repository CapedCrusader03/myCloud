from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse
import os
from typing import Optional
import asyncio
import json
from redis_config import redis_client
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, async_session
from services import upload_service, auth_service
from services.auth_service import get_current_user
from models.domain import User
from pydantic import BaseModel
from typing import Optional
from middleware import rate_limiter

router = APIRouter(prefix="/uploads", tags=["Uploads"])

class InitiateUploadRequest(BaseModel):
    filename: str
    total_size: int
    chunk_size: int
    file_checksum: str

class ShareRequest(BaseModel):
    ttl_hours: Optional[int] = 24
    max_downloads: Optional[int] = None

@router.get("")
async def list_uploads(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await upload_service.list_uploads(db, current_user.id)

@router.post("", dependencies=[Depends(rate_limiter)])
async def initiate_upload(
    request: InitiateUploadRequest, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    res = await upload_service.initiate_upload(
        db=db,
        user_id=current_user.id,
        filename=request.filename,
        total_size=request.total_size,
        chunk_size=request.chunk_size,
        file_checksum=request.file_checksum
    )
    return res

@router.patch("/{upload_id}/chunks/{chunk_index}", dependencies=[Depends(rate_limiter)])
async def receive_chunk(
    upload_id: str, 
    chunk_index: int, 
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    raw_data = await request.body()
    
    res = await upload_service.process_incoming_chunk(
        db=db, 
        upload_id=upload_id, 
        chunk_index=chunk_index, 
        raw_data=raw_data
    )
    
    if res:
        return {"message": f"Received chunk {chunk_index} for {upload_id}"}
    return {"message": f"Upload not found or failed"}

@router.get("/{upload_id}")
async def get_upload_status(
    upload_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    upload = await upload_service.get_upload_status(db, upload_id)
    if not upload or upload.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Upload not found")
        
    return await upload_service.get_upload_status_dict(upload)


@router.head("/{upload_id}")
async def resume_upload_status(
    upload_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    upload = await upload_service.get_upload_status(db, upload_id)
    if not upload or upload.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Upload not found")
        
    res = await upload_service.get_upload_status_dict(upload)
    received_chunks = res["received_chunks"]
    headers = {
        "Upload-Offset": str(len(received_chunks) * upload.chunk_size),
        "X-Missing-Chunks": ",".join(map(str, [i for i in range(upload.total_chunks) if i not in received_chunks]))
    }
    from fastapi.responses import Response
    return Response(headers=headers)

@router.delete("/{upload_id}")
async def delete_upload(
    upload_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    res = await upload_service.delete_upload(db, upload_id, user_id=current_user.id)
    if res:
        return {"message": f"Upload {upload_id} has been permanently deleted."}
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Upload not found")



@router.get("/{upload_id}/events")
async def stream_upload_events(upload_id: str):
    """
    Server-Sent Events (SSE) endpoint to stream progress.
    The browser's frontend uses 'new EventSource("/uploads/{id}/events")'
    """
    async def event_generator():
        # 1. Immediate flush to establish connection
        yield ": ok\n\n"
        
        # 2. INITIAL SYNC: Send the current state from DB instantly!
        async with async_session() as db_session:
            upload = await upload_service.get_upload_status(db_session, upload_id)
            if upload:
                status_dict = await upload_service.get_upload_status_dict(upload)
                status_dict["event_type"] = "INITIAL_SYNC"
                status_dict["percent"] = (len(status_dict["received_chunks"]) / upload.total_chunks * 100) if upload.total_chunks > 0 else 0
                yield f"data: {json.dumps(status_dict)}\n\n"
        
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"upload:{upload_id}")
        
        try:
            # 2. Use the async iterator for cleaner message handling
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
        except asyncio.CancelledError:
            await pubsub.unsubscribe(f"upload:{upload_id}")
            await pubsub.close()
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/{upload_id}/token")
async def get_download_token(upload_id: str, db: AsyncSession = Depends(get_db)):
    token = await upload_service.generate_download_token(db, upload_id)
    if token:
        return {"token": token}
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Upload not found or not complete")

# Note: This is an APIRouter prefixed with /uploads, but for the download link, 
# we might want a cleaner /download/{token} path.
# For now, I'll add it to this router to keep things simple, 
# so it will be reachable at /uploads/download/{token}.
@router.get("/download/{token}")
async def download_file(token: str, db: AsyncSession = Depends(get_db)):
    upload_id = await upload_service.validate_download_token(db, token)
    if not upload_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get upload info for filename
    upload = await upload_service.get_upload_status(db, str(upload_id))
    if not upload:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")
        
    filename = upload.filename
    file_path = f"chunks/{upload_id}_{filename}"
    
    if not os.path.exists(file_path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Physical file not found on disk")
        
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )

@router.post("/{upload_id}/share")
async def share_upload(
    upload_id: str, 
    request: ShareRequest, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify ownership before creating share link
    upload = await upload_service.get_upload_status(db, upload_id)
    if not upload or upload.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Upload not found")
        
    slug = await upload_service.create_share_link(
        db, 
        upload_id, 
        ttl_hours=request.ttl_hours, 
        max_downloads=request.max_downloads
    )
    if slug:
        return {"slug": slug, "share_url": f"/s/{slug}"}
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Upload not found or not complete")

@router.get("/s/{slug}", include_in_schema=False)
async def resolve_share(slug: str, db: AsyncSession = Depends(get_db)):
    # Note: We use include_in_schema=False because this is a vanity URL
    token, status = await upload_service.resolve_share_link(db, slug)
    
    if status == "OK":
        return RedirectResponse(url=f"/uploads/download/{token}")
    
    from fastapi import HTTPException
    if status == "EXPIRED":
        raise HTTPException(status_code=410, detail="Share link has expired")
    if status == "LIMIT_REACHED":
        raise HTTPException(status_code=403, detail="Download limit reached for this link")
    
    raise HTTPException(status_code=404, detail="Share link not found")
