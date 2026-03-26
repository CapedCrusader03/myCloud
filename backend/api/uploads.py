from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
import asyncio
import json
from redis_config import redis_client
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, async_session
from services import upload_service
from pydantic import BaseModel
from middleware import rate_limiter

router = APIRouter(prefix="/uploads", tags=["Uploads"])

class InitiateUploadRequest(BaseModel):
    filename: str
    total_size: int
    chunk_size: int
    file_checksum: str

@router.post("", dependencies=[Depends(rate_limiter)])
async def initiate_upload(request: InitiateUploadRequest, db: AsyncSession = Depends(get_db)):
    res = await upload_service.initiate_upload(
        db=db,
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
    db: AsyncSession = Depends(get_db)
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
async def get_upload_status(upload_id: str, db: AsyncSession = Depends(get_db)):
    res = await upload_service.get_upload_status(db, upload_id)
    if res:
        return res
    return {"message": "Upload not found"}, 404

@router.delete("/{upload_id}")
async def cancel_upload(upload_id: str, db: AsyncSession = Depends(get_db)):
    res = await upload_service.cancel_upload(db, upload_id)
    if res:
        return {"message": f"Upload {upload_id} has been cancelled and chunks deleted."}
    return {"message": "Upload not found"}, 404

@router.head("/{upload_id}", status_code=200)
async def resume_upload_status(upload_id: str, response: Response, db: AsyncSession = Depends(get_db)):
    # Re-use our GET status logic to find what's missing
    res = await upload_service.get_upload_status(db, upload_id)
    if not res:
        response.status_code = 404
        return
        
    received_set = set(res["received_chunks"])
    missing_chunks = [str(i) for i in range(1, res["total_chunks"] + 1) if i not in received_set]
    
    # Send instructions back to the client via HTTP headers
    response.headers["Upload-Offset"] = str(len(received_set))
    response.headers["X-Missing-Chunks"] = ",".join(missing_chunks)
    return

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
            status = await upload_service.get_upload_status(db_session, upload_id)
            if status:
                # Add an event_type so the frontend knows how to parse it consistently
                status["event_type"] = "INITIAL_SYNC"
                status["percent"] = (len(status["received_chunks"]) / status["total_chunks"] * 100) if status["total_chunks"] > 0 else 0
                yield f"data: {json.dumps(status)}\n\n"
        
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
