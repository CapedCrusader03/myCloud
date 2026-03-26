import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Upload as UploadIcon, File as FileIcon, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB chunks

interface UploadState {
  id: string;
  filename: string;
  percent: number;
  status: 'uploading' | 'assembling' | 'complete' | 'error' | 'idle';
  totalChunks: number;
  receivedChunks: number;
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<UploadState | null>(null);
  const [dragActive, setDragActive] = useState(false);

  // SSE Listener: Connect to the backend for real-time updates
  useEffect(() => {
    if (!upload?.id || upload.status === 'complete' || upload.status === 'error') return;

    console.log(`Subscribing to events for ${upload.id}`);
    const eventSource = new EventSource(`${API_BASE}/uploads/${upload.id}/events`);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('SSE update:', data.event_type, data);
      
      setUpload(prev => {
        if (!prev && data.event_type !== 'INITIAL_SYNC') return null;
        
        // If it's the first connection (Initial Sync), we populate everything.
        // Otherwise, we merge the specific event data.
        const base = prev || {
            id: data.upload_id,
            filename: data.filename || 'Unknown',
            percent: 0,
            status: 'idle' as 'idle',
            totalChunks: data.total_chunks || 0,
            receivedChunks: data.received_chunks ? (Array.isArray(data.received_chunks) ? data.received_chunks.length : data.received_chunks) : 0
        };

        return {
          ...base,
          status: data.status,
          percent: data.percent ?? base.percent,
          receivedChunks: data.received_chunks ? (Array.isArray(data.received_chunks) ? data.received_chunks.length : data.received_chunks) : base.receivedChunks,
          totalChunks: data.total_chunks ?? base.totalChunks
        };
      });

      if (data.status === 'complete' || data.status === 'error' || data.event_type === 'UPLOAD_CANCELLED') {
        if (data.event_type !== 'INITIAL_SYNC' || data.status === 'complete') {
           // We might want to keep the connection open for a bit, 
           // but for now close on terminal states if not just syncing.
           if (data.status === 'complete') eventSource.close();
        }
      }
    };

    eventSource.onerror = () => {
      console.error('SSE connection failed');
      eventSource.close();
    };

    return () => eventSource.close();
  }, [upload?.id, upload?.status]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const calculateChecksum = async (file: File) => {
    // For a real production app, we'd use a library like SparkMD5 or crypto.subtle
    // For this demo, let's use a dummy checksum or just its name+size hash
    return `sha256-${file.name}-${file.size}`;
  };

  const startUpload = async () => {
    if (!file) return;

    try {
      const checksum = await calculateChecksum(file);
      
      // 1. Initial Handshake: Create the upload record
      const initResp = await axios.post(`${API_BASE}/uploads`, {
        filename: file.name,
        total_size: file.size,
        chunk_size: CHUNK_SIZE,
        file_checksum: checksum
      });
      
      const uploadId = initResp.data.upload_id;
      
      // 2. Resumability Check: HEAD request to see where we are
      const headResp = await axios.head(`${API_BASE}/uploads/${uploadId}`);
      const missingChunks = headResp.headers['x-missing-chunks'] 
        ? headResp.headers['x-missing-chunks'].split(',').map(Number)
        : [];

      setUpload({
        id: uploadId,
        filename: file.name,
        percent: 0,
        status: 'uploading',
        totalChunks: Math.ceil(file.size / CHUNK_SIZE),
        receivedChunks: 0
      });

      // 3. Chunked Upload Sequence
      await uploadChunks(file, uploadId, headResp.headers['x-missing-chunks'] ? missingChunks : null);
      
    } catch (err) {
      console.error('Upload initiation failed', err);
      alert("Rate limit exceeded or server error! Try again in a few seconds.");
    }
  };

  const uploadChunks = async (file: File, uploadId: string, missingArray: number[] | null) => {
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    
    for (let i = 1; i <= totalChunks; i++) {
        // If we have a list of missing chunks (from a resume), skip the ones we already have
        if (missingArray && !missingArray.includes(i)) {
            continue;
        }

        const start = (i - 1) * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, file.size);
        const chunk = file.slice(start, end);

        try {
            await axios.patch(`${API_BASE}/uploads/${uploadId}/chunks/${i}`, chunk, {
                headers: { 'Content-Type': 'application/octet-stream' }
            });
        } catch (err) {
            console.error(`Failed to upload chunk ${i}`, err);
            // In a pro app, we'd add retry logic here
            return;
        }
    }
  };

  return (
    <div className="glass-card">
      <h1>myCloud</h1>
      <p className="subtitle">High-performance resumable file transfers.</p>

      {!upload ? (
        <div 
          className={`drop-zone ${dragActive ? 'active' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => { e.preventDefault(); setDragActive(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); }}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          <input type="file" id="file-input" hidden onChange={handleFileChange} />
          <UploadIcon size={48} />
          <div>
            <p style={{ fontSize: '1.2rem', fontWeight: 600 }}>{file ? file.name : 'Drop your file here'}</p>
            <p style={{ color: 'var(--text-dim)', marginTop: '0.5rem' }}>
              {file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : 'or click to browse local files'}
            </p>
          </div>
          {file && <button className="btn" onClick={(e) => {e.stopPropagation(); startUpload();}}>Start Transfer</button>}
        </div>
      ) : (
        <div className="upload-item">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <FileIcon size={24} color="var(--primary)" />
              <div>
                <p style={{ fontWeight: 600 }}>{upload.filename}</p>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-dim)' }}>
                  {upload.receivedChunks} / {upload.totalChunks} chunks uploaded
                </p>
              </div>
            </div>
            <span className={`status-badge status-${upload.status}`}>
              {upload.status}
            </span>
          </div>

          <div className="progress-container">
            <div className="progress-bar" style={{ width: `${upload.percent}%` }} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--primary)' }}>
              {upload.percent.toFixed(1)}% Complete
            </p>
            {upload.status === 'uploading' && <Loader2 className="animate-spin" size={18} />}
            {upload.status === 'complete' && <CheckCircle size={18} color="var(--success)" />}
            {upload.status === 'error' && <AlertCircle size={18} color="var(--error)" />}
          </div>
          
          {upload.status === 'complete' && (
            <button className="btn" style={{ marginTop: '1.5rem', width: '100%' }} onClick={() => {setUpload(null); setFile(null);}}>
              Upload Another File
            </button>
          )}
        </div>
      )}

      <style>{`
        .animate-spin {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
