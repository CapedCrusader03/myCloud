from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from services import upload_service
from pydantic import BaseModel

router = APIRouter(prefix="/uploads", tags=["Uploads"])

class InitiateUploadRequest(BaseModel):
    filename: str
    total_size: int
    chunk_size: int
    file_checksum: str

@router.post("")
async def initiate_upload(request: InitiateUploadRequest, db: AsyncSession = Depends(get_db)):
    res = await upload_service.initiate_upload(
        db=db,
        filename=request.filename,
        total_size=request.total_size,
        chunk_size=request.chunk_size,
        file_checksum=request.file_checksum
    )
    return res

@router.patch("/{upload_id}/chunks/{chunk_index}")
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
