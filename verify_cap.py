import requests
import json

API_BASE = "http://localhost:8000"

def get_token():
    res = requests.post(f"{API_BASE}/auth/login", data={"username": "success@example.com", "password": "password123"})
    if res.status_code != 200:
        print(f"Login failed: {res.text}")
        exit(1)
    return res.json()["access_token"]

def test_cap():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Try 6 GB (should fail)
    print("Testing 6 GB upload initiation...")
    payload_huge = {
        "filename": "huge_file.zip",
        "total_size": 6 * 1024 * 1024 * 1024,
        "chunk_size": 5 * 1024 * 1024,
        "file_checksum": "dummy-checksum"
    }
    res_huge = requests.post(f"{API_BASE}/uploads", json=payload_huge, headers=headers)
    print(f"Status: {res_huge.status_code}")
    print(f"Body: {res_huge.text}")
    
    if res_huge.status_code == 400 and "Storage limit exceeded" in res_huge.text:
        print("SUCCESS: 6 GB upload rejected as expected.")
    else:
        print("FAILURE: 6 GB upload was not rejected correctly.")

    # 2. Try 10 MB (should succeed)
    print("\nTesting 10 MB upload initiation...")
    payload_small = {
        "filename": "small_file.zip",
        "total_size": 10 * 1024 * 1024,
        "chunk_size": 5 * 1024 * 1024,
        "file_checksum": "dummy-checksum"
    }
    res_small = requests.post(f"{API_BASE}/uploads", json=payload_small, headers=headers)
    print(f"Status: {res_small.status_code}")
    
    if res_small.status_code == 200:
        print("SUCCESS: 10 MB upload initiated successfully.")
        # Cleanup (delete the upload record)
        upload_id = res_small.json()["upload_id"]
        requests.delete(f"{API_BASE}/uploads/{upload_id}", headers=headers)
    else:
        print("FAILURE: 10 MB upload failed.")

if __name__ == "__main__":
    test_cap()
