import httpx
import asyncio
import hashlib

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        chunk1 = b"Hello, this is "
        chunk2 = b"a split test file!"
        full_data = chunk1 + chunk2
        expected_checksum = hashlib.sha256(full_data).hexdigest()
        
        print("=== Test 1: Successful Validation ===")
        print("1. Initiating upload...")
        resp = await client.post("/uploads", json={
            "filename": "hello_world.txt",
            "total_size": len(full_data),
            "chunk_size": max(len(chunk1), len(chunk2)), # Ensures exact 2 chunk calculation
            "file_checksum": expected_checksum
        })
        resp.raise_for_status()
        upload_id = resp.json()["upload_id"]
        print(f"   => Upload ID: {upload_id}")
        
        print("2. Uploading chunk 1...")
        await client.patch(f"/uploads/{upload_id}/chunks/1", content=chunk1)
        
        print("3. Uploading chunk 2...")
        await client.patch(f"/uploads/{upload_id}/chunks/2", content=chunk2)
        
        print("4. Polling status (Should be 'complete')...")
        status_resp = await client.get(f"/uploads/{upload_id}")
        status_data = status_resp.json()
        print(f"   => Final Status: {status_data['status']}")
        if status_data["status"] == "complete":
            print("   => SUCCESS! The file was assembled and validated.")
        else:
            print("   => FAILED! Status is not complete.")

        print("\n=== Test 2: Corrupted Upload ===")
        print("1. Initiating upload with deliberately bad checksum...")
        resp_bad = await client.post("/uploads", json={
            "filename": "bad.txt",
            "total_size": len(chunk1),
            "chunk_size": len(chunk1),
            "file_checksum": "fake_checksum_123"
        })
        bad_id = resp_bad.json()["upload_id"]
        
        print("2. Uploading chunk 1...")
        await client.patch(f"/uploads/{bad_id}/chunks/1", content=chunk1)
        
        print("3. Checking status (Should be 'corrupted')...")
        status_resp_bad = await client.get(f"/uploads/{bad_id}")
        bad_status = status_resp_bad.json()["status"]
        print(f"   => Corrupted Final Status: {bad_status}")
        if bad_status == "corrupted":
            print("   => SUCCESS! The assembly correctly caught the bad checksum.")
        else:
            print(f"   => FAILED! Expected corrupted but got {bad_status}.")

if __name__ == "__main__":
    asyncio.run(main())
