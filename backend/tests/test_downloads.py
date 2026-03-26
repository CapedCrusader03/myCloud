import httpx
import asyncio
import hashlib
import time

async def test_full_download_flow():
    base_url = "http://localhost:8000"
    filename = f"test_download_{int(time.time())}.bin"
    file_content = b"This is the content of the file used for testing downloads! " * 1024 # ~64KB
    file_checksum = hashlib.sha256(file_content).hexdigest()
    
    print(f"1. Initiating upload for {filename}...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(f"{base_url}/uploads", json={
            "filename": filename,
            "total_size": len(file_content),
            "chunk_size": len(file_content),
            "file_checksum": file_checksum
        })
        assert res.status_code == 200, f"Initiate failed: {res.status_code} {res.text}"
        upload_id = res.json()["upload_id"]
        print(f"   => Upload ID: {upload_id}")
        
        print("2. Uploading the single chunk...")
        res = await client.patch(f"{base_url}/uploads/{upload_id}/chunks/1", content=file_content)
        assert res.status_code == 200, f"Chunk upload failed: {res.status_code} {res.text}"
        
        print("3. Waiting for assembly...")
        # Give it a bit more time
        time.sleep(3)
        
        print("4. Verifying upload is complete...")
        res = await client.get(f"{base_url}/uploads/{upload_id}")
        assert res.status_code == 200, f"Status check failed: {res.status_code} {res.text}"
        assert res.json()["status"] == "complete", f"Upload not complete: {res.json()}"
        
        print("5. Requesting download token...")
        res = await client.get(f"{base_url}/uploads/{upload_id}/token")
        assert res.status_code == 200, f"Token request failed: {res.status_code} {res.text}"
        token = res.json()["token"]
        print(f"   => Token obtained: {token[:20]}...")
        
        print("6. Executing download via token...")
        res = await client.get(f"{base_url}/uploads/download/{token}")
        assert res.status_code == 200, f"Download failed: {res.status_code} {res.text}"
        assert res.content == file_content
        print("   => SUCCESS: Downloaded content matches original exactly!")
        
        print("7. Testing invalid token...")
        res = await client.get(f"{base_url}/uploads/download/this_is_a_fake_token")
        assert res.status_code == 401, f"Invalid token not rejected with 401 (got {res.status_code})"
        print("   => SUCCESS: Invalid token rejected.")

if __name__ == "__main__":
    asyncio.run(test_full_download_flow())
