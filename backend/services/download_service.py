"""
Download service.

Handles download token generation and validation.
Separated from upload_service for single-responsibility.
"""

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from models.domain import Upload, DownloadToken


async def generate_download_token(db: AsyncSession, upload_id: str) -> str | None:
    """Generate a time-limited JWT download token for a completed upload."""
    try:
        uid = uuid.UUID(upload_id)
    except ValueError:
        return None

    upload = await db.get(Upload, uid)
    if not upload or upload.status != "complete":
        return None

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.download_token_expire_minutes
    )

    payload = {
        "upload_id": str(upload.id),
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }

    token_str = jwt.encode(
        payload, settings.download_token_secret_key, algorithm=settings.jwt_algorithm
    )

    db_token = DownloadToken(
        upload_id=upload.id,
        token=token_str,
        expires_at=expires_at,
    )
    db.add(db_token)
    await db.commit()

    return token_str


async def validate_download_token(db: AsyncSession, token: str) -> uuid.UUID | None:
    """Validate a download token JWT and return the upload_id if valid."""
    try:
        payload = jwt.decode(
            token,
            settings.download_token_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        upload_id = payload.get("upload_id")
    except JWTError:
        return None

    stmt = select(DownloadToken).where(DownloadToken.token == token)
    result = await db.execute(stmt)
    db_token = result.scalar_one_or_none()

    if not db_token or db_token.expires_at < datetime.now(timezone.utc):
        return None

    return db_token.upload_id
