"""
Share link service.

Handles creation and resolution of time-limited, optionally
download-capped share links.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.domain import Upload, ShareLink
from services.download_service import generate_download_token


def generate_slug(length: int = 8) -> str:
    """Generate a cryptographically secure URL-safe slug."""
    return secrets.token_urlsafe(length)[:length]


async def create_share_link(
    db: AsyncSession,
    upload_id: str,
    ttl_hours: int = 24,
    max_downloads: int | None = None,
) -> str | None:
    """Create a share link for a completed upload. Returns the slug or None."""
    try:
        uid = uuid.UUID(upload_id)
    except ValueError:
        return None

    upload = await db.get(Upload, uid)
    if not upload or upload.status != "complete":
        return None

    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    slug = generate_slug()

    # Collision check — regenerate with longer slug if needed
    stmt = select(ShareLink).where(ShareLink.slug == slug)
    if await db.scalar(stmt):
        slug = generate_slug(length=12)

    db_share = ShareLink(
        upload_id=upload.id,
        slug=slug,
        max_downloads=max_downloads,
        expires_at=expires_at,
    )
    db.add(db_share)
    await db.commit()

    return slug


async def resolve_share_link(
    db: AsyncSession, slug: str
) -> tuple[str | None, str]:
    """
    Resolve a share slug to a download token.
    Returns (token, status_string).
    """
    stmt = select(ShareLink).where(ShareLink.slug == slug)
    result = await db.execute(stmt)
    share = result.scalar_one_or_none()

    if not share:
        return None, "NOT_FOUND"

    if share.expires_at < datetime.now(timezone.utc):
        return None, "EXPIRED"

    if share.max_downloads is not None and share.download_count >= share.max_downloads:
        return None, "LIMIT_REACHED"

    # Atomic increment
    share.download_count += 1
    await db.commit()

    token = await generate_download_token(db, str(share.upload_id))
    return token, "OK"
