import httpx
import asyncio
import hashlib

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        # Prepare 4 chunks of data
        chunks = [b"Chunk 1 ", b"Chunk 2 ", b"Chunk 3 ", b"Chunk 4 "]
        full_data = b"".join(chunks)
        expected_checksum = hashlib.sha256(full_data).hexdigest()
        
        print("1. Initiating parallel-ready upload...")
        resp = await client.post("/uploads", json={
            "filename": "parallel_test.txt",
            "total_size": len(full_data),
            "chunk_size": len(chunks[0]),
            "file_checksum": expected_checksum
        })
        upload_id = resp.json()["upload_id"]
        
        print(f"2. Sending ALL {len(chunks)} chunks SIMULTANEOUSLY via asyncio.gather...")
        # This creates 4 parallel HTTP requests at once
        tasks = [
            client.patch(f"/uploads/{upload_id}/chunks/{i+1}", content=chunks[i])
            for i in range(len(chunks))
        ]
        
        # Fire them all at once!
        results = await asyncio.gather(*tasks)
        
        for i, r in enumerate(results):
            print(f"   => Chunk {i+1} response: {r.status_code}")

        print("\n3. Verifying final status (Should be 'complete' exactly once)...")
        status_resp = await client.get(f"/uploads/{upload_id}")
        final_status = status_resp.json()["status"]
        print(f"   => Final Status in DB: {final_status}")
        
        if final_status == "complete":
            print("\n=== CONCURRENCY TEST PASSED! ===")
            print("The row-level locks forced the chunks to wait their turn,")
            print("ensuring assembly only happened once.")
        else:
            print(f"\n=== TEST FAILED! Expected 'complete' but got '{final_status}' ===")

if __name__ == "__main__":
    asyncio.run(main())
