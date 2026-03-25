import pytest
from sqlalchemy import text

@pytest.mark.asyncio
async def test_uploads_table_exists(db):
    result = await db.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='uploads'
    """))
    
    columns = [row[0] for row in result.fetchall()]
    
    expected_columns = [
        "id", "filename", "total_size", "chunk_size",
        "total_chunks", "file_checksum", "status",
        "api_key", "created_at", "expires_at"
    ]
    assert all(c in columns for c in expected_columns)