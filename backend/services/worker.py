import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database import async_session
from models.domain import Upload

logger = logging.getLogger(__name__)

async def cleanup_stale_assemblies():
    """
    Finds uploads stuck in 'assembling' status for more than 10 minutes
    and resets them to 'uploading' so they can be retried.
    """
    while True:
        try:
            async with async_session() as db:
                # Find uploads in 'assembling' state for more than 10 minutes
                stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
                
                # Note: We'd need an 'updated_at' column for better precision, 
                # but for now we'll use 'created_at' as a proxy or just assume stalled.
                # Let's assume we add an 'updated_at' or just use a simple time check.
                # For this MVP, let's just look for 'assembling' status.
                
                stmt = select(Upload).where(
                    Upload.status == "assembling",
                    Upload.created_at < stale_threshold
                )
                
                result = await db.execute(stmt)
                stale_uploads = result.scalars().all()
                
                for upload in stale_uploads:
                    logger.warning(f"Resetting stale assembly for upload {upload.id}")
                    upload.status = "uploading"
                
                if stale_uploads:
                    await db.commit()
                    
        except Exception as e:
            logger.error(f"Error in cleanup worker: {e}")
            
        # Sleep for 5 minutes before checking again
        await asyncio.sleep(300)

async def start_worker():
    logger.info("Starting background worker...")
    asyncio.create_task(cleanup_stale_assemblies())
