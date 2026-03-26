import httpx
import asyncio

async def test_rate_limit():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        print("1. Rapidly firing 15 requests (Bucket capacity is 10)...")
        
        tasks = [
            client.post("/uploads", json={
                "filename": f"limit_test_{i}.txt",
                "total_size": 100,
                "chunk_size": 50,
                "file_checksum": "none"
            })
            for i in range(15)
        ]
        
        responses = await asyncio.gather(*tasks)
        
        status_codes = [r.status_code for r in responses]
        success_count = status_codes.count(200)
        failure_count = status_codes.count(429)
        
        print(f"   => Success (200): {success_count}")
        print(f"   => Rate Limited (429): {failure_count}")
        
        if failure_count > 0:
            print("\n=== RATE LIMIT TEST PASSED! ===")
            print("The Token Bucket correctly rejected 'burst' traffic once reaching capacity.")
        else:
            print("\n=== RATE LIMIT TEST FAILED! ===")

if __name__ == "__main__":
    asyncio.run(test_rate_limit())
