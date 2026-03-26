import httpx
import asyncio
import hashlib
import time

async def test_share_link_flow():
    base_url = "http://localhost:8000"
    filename = f"share_test_{int(time.time())}.txt"
    file_content = b"Public share link test content!"
    file_checksum = hashlib.sha256(file_content).hexdigest()
    
    print(f"1. Preparing file {filename}...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Initiate
        res = await client.post(f"{base_url}/uploads", json={
            "filename": filename,
            "total_size": len(file_content),
            "chunk_size": len(file_content),
            "file_checksum": file_checksum
        })
        upload_id = res.json()["upload_id"]
        
        # Upload
        await client.patch(f"{base_url}/uploads/{upload_id}/chunks/1", content=file_content)
        time.sleep(2) # assembly
        
        print("2. Creating a Share Link with max_downloads=2...")
        res = await client.post(f"{base_url}/uploads/{upload_id}/share", json={
            "ttl_hours": 1,
            "max_downloads": 2
        })
        assert res.status_code == 200
        slug = res.json()["slug"]
        share_url = f"{base_url}/uploads/s/{slug}"
        print(f"   => Slug: {slug}")
        
        print("3. Attempting 1st download (should follow redirect)...")
        res = await client.get(share_url, follow_redirects=True)
        assert res.status_code == 200, f"1st download failed: {res.status_code} {res.text}"
        assert res.content == file_content
        print("   => Success 1!")
        
        print("4. Attempting 2nd download...")
        res = await client.get(share_url, follow_redirects=True)
        assert res.status_code == 200, f"2nd download failed: {res.status_code} {res.text}"
        assert res.content == file_content
        print("   => Success 2!")
        
        print("5. Attempting 3rd download (should be BLOCKED)...")
        res = await client.get(share_url, follow_redirects=True)
        # It should hit the 403 Forbidden in the redirector
        assert res.status_code == 403
        print("   => SUCCESS: 3rd download blocked by limit.")
        
        print("6. Testing invalid slug...")
        res = await client.get(f"{base_url}/uploads/s/this_slug_does_not_exist")
        assert res.status_code == 404
        print("   => SUCCESS: Invalid slug rejected.")

if __name__ == "__main__":
    asyncio.run(test_share_link_flow())
