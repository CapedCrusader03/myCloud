import httpx
import asyncio
import time

async def test_rate_limiter():
    url = "http://localhost:8000/uploads"
    # Dummy data for initiate upload
    payload = {
        "filename": "test.txt",
        "total_size": 100,
        "chunk_size": 10,
        "file_checksum": "dummy"
    }
    
    print("--- Phase 1: Rapid Fire (Expected: 10 Success, 10 Failure) ---")
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(20):
            tasks.append(client.post(url, json=payload))
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        limit_count = 0
        other_count = 0
        
        for i, resp in enumerate(responses):
            if isinstance(resp, httpx.Response):
                if resp.status_code == 200:
                    success_count += 1
                elif resp.status_code == 429:
                    limit_count += 1
                else:
                    other_count += 1
                    print(f"Request {i}: Unexpected status {resp.status_code}")
            else:
                print(f"Request {i}: Exception {resp}")
                
        print(f"Results: Successes={success_count}, 429 Errors={limit_count}")
        
    print("\n--- Phase 2: Refill Check (Wait 1s, expect ~2 success) ---")
    time.sleep(1.1)
    
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(5):
            tasks.append(client.post(url, json=payload))
            
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        for resp in responses:
            if isinstance(resp, httpx.Response) and resp.status_code == 200:
                success_count += 1
        
        print(f"Refill Results: Successes after 1s={success_count}")

if __name__ == "__main__":
    asyncio.run(test_rate_limiter())
