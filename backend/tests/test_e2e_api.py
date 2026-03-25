import httpx
import asyncio
import os

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Initiate Upload
        print("1. Initiating upload via POST /uploads...")
        resp = await client.post("/uploads", json={
            "filename": "hello.txt",
            "total_size": 100,
            "chunk_size": 10,
            "file_checksum": "dummy"
        })
        resp.raise_for_status()
        upload_id = resp.json()["upload_id"]
        print(f"   => Got Upload ID: {upload_id}")
        
        # 2. Upload Chunk
        print("\n2. Uploading chunk 1 via PATCH /uploads/{id}/chunks/1...")
        chunk_data = b"Hello, this is my raw binary data!"
        resp2 = await client.patch(f"/uploads/{upload_id}/chunks/1", content=chunk_data)
        resp2.raise_for_status()
        print(f"   => Response: {resp2.json()}")
        
        # 3. Verify on Disk
        print("\n3. Verifying the chunk was written to disk...")
        chunk_path = f"/app/chunks/{upload_id}/1.part"
        if os.path.exists(chunk_path):
            with open(chunk_path, "rb") as f:
                saved_data = f.read()
            print(f"   => SUCCESS! File exists on disk at {chunk_path}")
            print(f"   => Data inside file: {saved_data.decode()}")
        else:
            print(f"   => FAILED! Could not find {chunk_path} on disk.")

if __name__ == "__main__":
    asyncio.run(main())
