"""
File management service.

Handles listing and deletion of completed uploads.
"""

import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.domain import Upload
from services import storage_service

logger = logging.getLogger(__name__)


async def list_uploads(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """List all completed uploads for a user, newest first."""
    stmt = (
        select(Upload)
        .where(Upload.status == "complete", Upload.user_id == user_id)
        .order_by(Upload.created_at.desc())
    )
    result = await db.execute(stmt)
    uploads = result.scalars().all()

    return [
        {
            "upload_id": str(u.id),
            "filename": u.filename,
            "total_size": u.total_size,
            "created_at": u.created_at.isoformat(),
            "status": u.status,
        }
        for u in uploads
    ]


async def delete_upload(
    db: AsyncSession, upload_id: str, user_id: uuid.UUID | None = None
) -> bool:
    """
    Delete an upload and its physical file.
    Returns True on success, False if not found or not owned.
    """
    try:
        uid = uuid.UUID(upload_id)
    except ValueError:
        return False

    upload = await db.get(Upload, uid)
    if not upload:
        return False

    # Ownership check
    if user_id and upload.user_id != user_id:
        return False

    # Delete the physical file
    await storage_service.delete_final_file(str(upload.id), upload.filename)

    # Delete from DB (cascade handles tokens and share links)
    await db.delete(upload)
    await db.commit()

    return True
