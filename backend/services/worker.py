"""
Background worker for housekeeping tasks.

Periodically scans for stale uploads and recovers them.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.future import select

from database import async_session
from models.domain import Upload
from services.upload_service import broadcast_upload_event

logger = logging.getLogger(__name__)


async def cleanup_stale_assemblies() -> None:
    """
    Finds uploads stuck in 'assembling' for >10 minutes (based on updated_at)
    and resets them to 'uploading' so clients can retry.
    """
    while True:
        try:
            async with async_session() as db:
                stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)

                stmt = select(Upload).where(
                    Upload.status == "assembling",
                    Upload.updated_at < stale_threshold,
                )

                result = await db.execute(stmt)
                stale_uploads = result.scalars().all()

                for upload in stale_uploads:
                    logger.warning(
                        "Worker: Resetting stale upload %s to 'uploading'", upload.id
                    )
                    upload.status = "uploading"
                    await broadcast_upload_event(upload, "UPLOAD_RECOVERED")

                if stale_uploads:
                    await db.commit()

        except Exception:
            logger.exception("Error in cleanup worker")

        await asyncio.sleep(300)


async def start_worker() -> None:
    """Launch background tasks."""
    logger.info("Starting background worker...")
    asyncio.create_task(cleanup_stale_assemblies())
