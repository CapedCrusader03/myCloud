import httpx
import asyncio
import os

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Initiate Upload
        chunk_data = b"Hello, this is my raw binary data!"
        import hashlib
        real_checksum = hashlib.sha256(chunk_data).hexdigest()
        
        print("1. Initiating upload via POST /uploads...")
        resp = await client.post("/uploads", json={
            "filename": "hello.txt",
            "total_size": len(chunk_data),
            "chunk_size": 100, 
            "file_checksum": real_checksum
        })
        resp.raise_for_status()
        upload_id = resp.json()["upload_id"]
        print(f"   => Got Upload ID: {upload_id}")
        
        # 2. Upload Chunk
        print("\n2. Uploading chunk 1 via PATCH /uploads/{id}/chunks/1...")
        resp2 = await client.patch(f"/uploads/{upload_id}/chunks/1", content=chunk_data)
        resp2.raise_for_status()
        print(f"   => Response: {resp2.json()}")
        
        # 3. Verify status via GET /uploads/{id}
        print("\n3. Verifying the upload status via API...")
        await asyncio.sleep(1) # Give it a second to process assembly
        resp3 = await client.get(f"/uploads/{upload_id}")
        resp3.raise_for_status()
        status_data = resp3.json()
        print(f"   => Current Status: {status_data['status']}")
        if status_data['status'] in ['complete', 'assembling']:
            print("   => SUCCESS! Upload is progressing or complete.")
        else:
            print(f"   => FAILED! Unexpected status: {status_data['status']}")

if __name__ == "__main__":
    asyncio.run(main())
