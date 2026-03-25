import pytest
from sqlalchemy import text

@pytest.mark.asyncio
async def test_chunks_table_exists(db):
    result = await db.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='chunks'
    """))
    columns = [r[0] for r in result.fetchall()]
    assert all(c in columns for c in [
        "id", "upload_id", "chunk_index",
        "size", "checksum", "checksum_valid", "received_at"
    ])

@pytest.mark.asyncio
async def test_chunks_foreign_key(db):
    with pytest.raises(Exception):
        # Using a syntactically valid UUID that doesn't exist to explicitly test the FK
        await db.execute(text("INSERT INTO chunks (id, upload_id, chunk_index, size, checksum, checksum_valid, is_uploaded) VALUES ('123e4567-e89b-12d3-a456-426614174000', '00000000-0000-0000-0000-000000000000', 1, 1024, 'abc', true, false)"))