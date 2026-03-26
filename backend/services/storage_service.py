import os
import aiofiles
import hashlib
import asyncio
import shutil

CHUNK_DIR = "chunks"
# Ensure the root chunks directory exists
os.makedirs(CHUNK_DIR, exist_ok=True)

async def write_chunk(upload_id: str, chunk_index: int, data: bytes):
    """Writes raw bytes to chunks/{upload_id}/{chunk_index}.part"""
    
    # Create a subfolder specifically for this upload_id
    upload_dir = os.path.join(CHUNK_DIR, str(upload_id))
    os.makedirs(upload_dir, exist_ok=True)
    
    # Write the chunk file
    chunk_path = os.path.join(upload_dir, f"{chunk_index}.part")
    async with aiofiles.open(chunk_path, 'wb') as f:
        await f.write(data)

async def delete_chunks(upload_id: str):
    """Deletes the chunks directory for a given upload_id"""
    upload_dir = os.path.join(CHUNK_DIR, str(upload_id))
    if os.path.exists(upload_dir):
        # Run blocking rmtree in a background thread to prevent freezing the event loop
        await asyncio.to_thread(shutil.rmtree, upload_dir)

async def assemble_file(upload_id: str, total_chunks: int, final_filename: str):

    upload_dir = os.path.join(CHUNK_DIR, str(upload_id))
    final_path = os.path.join(CHUNK_DIR, f"{str(upload_id)}_{final_filename}")

    def _stitch():
        sha256_hash = hashlib.sha256()

        with open(final_path, "wb") as f:
            for i in range(1, total_chunks + 1):
                chunk_path = os.path.join(upload_dir, f"{i}.part")
                with open(chunk_path, "rb") as chunk_file:
                    chunk_data = chunk_file.read()
                    f.write(chunk_data)
                    sha256_hash.update(chunk_data)
        return sha256_hash.hexdigest()
    
    final_checksum = await asyncio.to_thread(_stitch)

    await delete_chunks(upload_id)

    return final_checksum

async def delete_final_file(upload_id: str, filename: str):
    """Deletes the assembled file from the chunks directory"""
    file_path = os.path.join(CHUNK_DIR, f"{str(upload_id)}_{filename}")
    if os.path.exists(file_path):
        await asyncio.to_thread(os.remove, file_path)
    