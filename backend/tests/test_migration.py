import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.future import select
from database import async_session
from models.domain import Upload, DownloadToken, ShareLink

async def test_migration_integrity():
    async with async_session() as db:
        print("1. Creating a mock upload...")
        u_id = uuid.uuid4()
        new_upload = Upload(
            id=u_id,
            filename="migration_test.txt",
            total_size=100,
            chunk_size=10,
            total_chunks=10,
            file_checksum="test-checksum",
            status="complete"
        )
        db.add(new_upload)
        await db.commit()
        
        print(f"2. Adding a DownloadToken for {u_id}...")
        token = DownloadToken(
            upload_id=u_id,
            token="test-jwt-token-string",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        db.add(token)
        
        print(f"3. Adding a ShareLink for {u_id}...")
        share = ShareLink(
            upload_id=u_id,
            slug="test-slug-123",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            max_downloads=5
        )
        db.add(share)
        await db.commit()
        
        print("4. Verifying records exist...")
        st_token = await db.execute(select(DownloadToken).where(DownloadToken.upload_id == u_id))
        assert st_token.scalar() is not None
        
        st_share = await db.execute(select(ShareLink).where(ShareLink.upload_id == u_id))
        assert st_share.scalar() is not None
        print("   => SUCCESS: Records created and linked correctly.")
        
        print("5. Testing CASCADE DELETE (Deleting Upload)...")
        await db.delete(new_upload)
        await db.commit()
        
        # Check if children are gone
        st_token_gone = await db.execute(select(DownloadToken).where(DownloadToken.upload_id == u_id))
        assert st_token_gone.scalar() is None
        
        st_share_gone = await db.execute(select(ShareLink).where(ShareLink.upload_id == u_id))
        assert st_share_gone.scalar() is None
        print("   => SUCCESS: Cascade delete removed linked tokens and share links.")

if __name__ == "__main__":
    asyncio.run(test_migration_integrity())
