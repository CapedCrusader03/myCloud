import httpx
import asyncio
import json

async def test_sse():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        # 1. Initiate an upload
        print("1. Initiating upload...")
        init_resp = await client.post("/uploads", json={
            "filename": "sse_test.txt",
            "total_size": 20,
            "chunk_size": 10,
            "file_checksum": "fake_checksum"
        })
        upload_id = init_resp.json()["upload_id"]
        
        # 2. Start a background task to listen to SSE
        print(f"2. Connecting to SSE for upload {upload_id}...")
        
        async def listen_to_sse():
            # Use a separate client for the long-lived stream
            async with httpx.AsyncClient(timeout=30.0) as sse_client:
                async with sse_client.stream("GET", f"http://localhost:8000/uploads/{upload_id}/events") as response:
                    print("   => SSE Connection established.")
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            print(f"   => RECEIVED SSE EVENT: {data.get('event_type')} {data}")
                            if data.get("event_type") == "CHUNK_RECEIVED":
                                return data
                            # Initial sync is fine too, but we wait for the chunk received event
                            if data.get("event_type") == "INITIAL_SYNC":
                                print("   => (Sync payload received)")

        # Start the listener
        listener_task = asyncio.create_task(listen_to_sse())
        
        # Wait a moment for connection to establish
        await asyncio.sleep(1)
        
        # 3. Upload a chunk
        print("3. Uploading Chunk 1...")
        await client.patch(f"/uploads/{upload_id}/chunks/1", content=b"1234567890")
        
        # 4. Wait for the event
        print("4. Waiting for SSE event...")
        event_data = await asyncio.wait_for(listener_task, timeout=5.0)
        
        if event_data and event_data["received_chunks"] == 1:
            print("\n=== SSE PROGRESS TEST PASSED! ===")
        else:
            print("\n=== SSE PROGRESS TEST FAILED ===")

async def test_sse_cancellation():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        # 1. Initiate
        init_resp = await client.post("/uploads", json={
            "filename": "cancel_test.txt", "total_size": 20, "chunk_size": 10, "file_checksum": "none"
        })
        upload_id = init_resp.json()["upload_id"]
        
        # 2. Listen
        async def listen_for_cancel():
            async with httpx.AsyncClient(timeout=30.0) as sse_client:
                async with sse_client.stream("GET", f"http://localhost:8000/uploads/{upload_id}/events") as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            if data.get("event_type") == "UPLOAD_CANCELLED":
                                return data

        listener_task = asyncio.create_task(listen_for_cancel())
        await asyncio.sleep(1)
        
        # 3. Kill it
        print(f"3. Cancelling upload {upload_id}...")
        await client.delete(f"/uploads/{upload_id}")
        
        # 4. Wait
        event_data = await asyncio.wait_for(listener_task, timeout=5.0)
        if event_data:
            print("=== SSE CANCELLATION TEST PASSED! ===")

if __name__ == "__main__":
    async def main():
        await test_sse()
        await test_sse_cancellation()
    asyncio.run(main())
