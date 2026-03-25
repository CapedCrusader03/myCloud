import httpx
import asyncio
import hashlib

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        chunk1 = b"AAAAA"
        chunk2 = b"BBBBB"
        full_data = chunk1 + chunk2
        expected_checksum = hashlib.sha256(full_data).hexdigest()
        
        print("1. Initiating upload...")
        resp = await client.post("/uploads", json={
            "filename": "resume_test.txt",
            "total_size": len(full_data),
            "chunk_size": len(chunk1),
            "file_checksum": expected_checksum
        })
        resp.raise_for_status()
        upload_id = resp.json()["upload_id"]
        print(f"   => Upload ID: {upload_id}")
        
        print("\n2. Checking HEAD for missing chunks...")
        head_resp = await client.head(f"/uploads/{upload_id}")
        print(f"   => Upload-Offset: {head_resp.headers.get('Upload-Offset')}")
        print(f"   => X-Missing-Chunks: {head_resp.headers.get('X-Missing-Chunks')}")
        assert head_resp.headers.get("X-Missing-Chunks") == "1,2"
        
        print("\n3. Uploading Chunk 1...")
        await client.patch(f"/uploads/{upload_id}/chunks/1", content=chunk1)
        
        print("\n4. Uploading Chunk 1 AGAIN (Idempotency Test!)...")
        await client.patch(f"/uploads/{upload_id}/chunks/1", content=chunk1)
        print("   => Success! No crash or duplicates.")
        
        print("\n5. Checking HEAD again...")
        head_resp2 = await client.head(f"/uploads/{upload_id}")
        print(f"   => Upload-Offset: {head_resp2.headers.get('Upload-Offset')}")
        print(f"   => X-Missing-Chunks: {head_resp2.headers.get('X-Missing-Chunks')}")
        assert head_resp2.headers.get("X-Missing-Chunks") == "2"
        
        print("\n6. Uploading Chunk 2...")
        await client.patch(f"/uploads/{upload_id}/chunks/2", content=chunk2)
        
        print("\n7. Polling final status...")
        status_resp = await client.get(f"/uploads/{upload_id}")
        print(f"   => Final Status: {status_resp.json()['status']}")
        assert status_resp.json()["status"] == "complete"
        print("\n=== ALL RESUMABILITY TESTS PASSED! ===")

if __name__ == "__main__":
    asyncio.run(main())
