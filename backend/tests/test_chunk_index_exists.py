import pytest
from sqlalchemy import text

@pytest.mark.asyncio
async def test_chunk_index_exists(db):
    result = await db.execute(text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename='chunks' AND indexdef LIKE '%chunk_index%'
    """))
    assert result.fetchone() is not None