import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  Upload as UploadIcon, 
  File as FileIcon, 
  CheckCircle, 
  AlertCircle, 
  Loader2, 
  Download, 
  Share2, 
  Copy,
  ExternalLink,
  LogIn,
  UserPlus,
  LogOut,
  User as UserIcon
} from 'lucide-react';

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

interface FileRecord {
  upload_id: string;
  filename: string;
  total_size: number;
  created_at: string;
  status: string;
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<UploadState | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [dashboardShareUrl, setDashboardShareUrl] = useState<string | null>(null);
  const [files, setFiles] = useState<FileRecord[]>([]);
  
  // Auth State
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [email, setEmail] = useState<string>(localStorage.getItem('userEmail') || '');
  const [authView, setAuthView] = useState<'login' | 'register'>('login');
  const [password, setPassword] = useState('');

  // Handle /s/{slug} share link routing — redirect to backend for resolution
  useEffect(() => {
    const path = window.location.pathname;
    if (path.startsWith('/s/')) {
      window.location.replace(`${API_BASE}${path}`);
    }
  }, []);

  // Configure Axios Defaults
  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      localStorage.setItem('token', token);
      localStorage.setItem('userEmail', email);
    } else {
      delete axios.defaults.headers.common['Authorization'];
      localStorage.removeItem('token');
      localStorage.removeItem('userEmail');
    }
  }, [token, email]);

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

  // Dashboard Fetch
  const fetchFiles = async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/uploads`);
      setFiles(data);
    } catch (err) {
      console.error("Failed to fetch files", err);
    }
  };

  useEffect(() => {
    if (token) {
      fetchFiles();
      const interval = setInterval(fetchFiles, 10000); 
      return () => clearInterval(interval);
    }
  }, [token]);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (authView === 'login') {
        const params = new URLSearchParams();
        params.append('username', email);
        params.append('password', password);
        const { data } = await axios.post(`${API_BASE}/auth/login`, params);
        setToken(data.access_token);
      } else {
        await axios.post(`${API_BASE}/auth/register`, { email, password });
        alert("Account created! Please login.");
        setAuthView('login');
      }
    } catch (err) {
      alert("Authentication failed. Check credentials.");
    }
  };

  const handleLogout = () => {
    setToken(null);
    setFiles([]);
    setUpload(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const calculateChecksum = async (file: File) => {
    const arrayBuffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
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
    for (let i = 0; i < totalChunks; i++) {
        // If we have a list of missing chunks (from a resume), skip the ones we already have
        if (missingArray && !missingArray.includes(i)) {
            continue;
        }

        const start = i * CHUNK_SIZE;
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

  const handleDownload = async () => {
    if (!upload?.id) return;
    try {
      const { data } = await axios.get(`${API_BASE}/uploads/${upload.id}/token`);
      // Start the download in a new tab/window
      window.open(`${API_BASE}/uploads/download/${data.token}`, '_blank');
    } catch (err) {
      console.error("Download failed", err);
      alert("Failed to get download token.");
    }
  };

  const handleShare = async () => {
    if (!upload?.id) return;
    try {
      const { data } = await axios.post(`${API_BASE}/uploads/${upload.id}/share`, {
        ttl_hours: 24, // 1 day default
        max_downloads: 5 // 5 downloads default
      });
      const fullUrl = `${window.location.origin}${data.share_url}`;
      setShareUrl(fullUrl);
    } catch (err) {
      console.error("Sharing failed", err);
      alert("Failed to create share link.");
    }
  };

  const copyToClipboard = () => {
    if (shareUrl) {
      navigator.clipboard.writeText(shareUrl);
      alert("Link copied to clipboard!");
    }
  };

  const handleDownloadFile = async (id: string) => {
    try {
      const { data } = await axios.get(`${API_BASE}/uploads/${id}/token`);
      window.open(`${API_BASE}/uploads/download/${data.token}`, '_blank');
    } catch (err) {
      alert("Failed to download.");
    }
  };

  const handleShareFile = async (id: string) => {
    try {
      const { data } = await axios.post(`${API_BASE}/uploads/${id}/share`, { ttl_hours: 24 });
      setDashboardShareUrl(`${window.location.origin}${data.share_url}`);
    } catch (err) {
      alert("Failed to share.");
    }
  };

  const handleDeleteFile = async (id: string) => {
    if (!confirm("Are you sure you want to delete this file permanently?")) return;
    try {
      await axios.delete(`${API_BASE}/uploads/${id}`);
      fetchFiles();
    } catch (err) {
      alert("Failed to delete.");
    }
  };

  if (!token) {
    return (
      <div className="glass-card auth-card">
        <h1>myCloud</h1>
        <p className="subtitle">{authView === 'login' ? 'Welcome back! Login to your drive.' : 'Create an account to start uploading.'}</p>
        
        <form onSubmit={handleAuth} className="auth-form">
          <input 
            type="email" 
            placeholder="Email Address" 
            value={email} 
            onChange={(e) => setEmail(e.target.value)} 
            required 
          />
          <input 
            type="password" 
            placeholder="Password" 
            value={password} 
            onChange={(e) => setPassword(e.target.value)} 
            required 
          />
          <button type="submit" className="btn">
            {authView === 'login' ? <LogIn size={18} /> : <UserPlus size={18} />}
            {authView === 'login' ? 'Login' : 'Register'}
          </button>
        </form>

        <p className="auth-switch" onClick={() => setAuthView(authView === 'login' ? 'register' : 'login')}>
          {authView === 'login' ? "Don't have an account? Register" : "Already have an account? Login"}
        </p>
      </div>
    );
  }

  return (
    <div className="glass-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>myCloud</h1>
          <p className="subtitle">High-performance resumable file transfers.</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button className="btn-secondary-sm" onClick={() => { setUpload(null); setFile(null); setShareUrl(null); }}>
            Dashboard
          </button>
          <div className="user-badge">
            <UserIcon size={14} />
            <span>{email}</span>
          </div>
          <button className="btn-logout" onClick={handleLogout} title="Logout">
            <LogOut size={18} />
          </button>
        </div>
      </div>

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
            <div className="actions-grid" style={{ marginTop: '1.5rem' }}>
              <button className="btn btn-secondary" onClick={handleDownload}>
                <Download size={18} /> Download
              </button>
              <button className="btn btn-secondary" onClick={handleShare}>
                <Share2 size={18} /> Share Link
              </button>
            </div>
          )}

          {shareUrl && (
            <div className="share-box">
              <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.5rem' }}>Public Share Link (Expires in 24h)</p>
              <div className="share-input-group">
                <input readOnly value={shareUrl} />
                <button onClick={copyToClipboard} title="Copy to clipboard">
                  <Copy size={16} />
                </button>
                <a href={shareUrl} target="_blank" rel="noreferrer" title="Open in new tab">
                  <ExternalLink size={16} />
                </a>
              </div>
            </div>
          )}
          
          {upload.status === 'complete' && (
            <button className="btn" style={{ marginTop: '1rem', width: '100%', background: 'transparent', border: '1px solid var(--glass-border)' }} onClick={() => {setUpload(null); setFile(null); setShareUrl(null);}}>
              ← Back to Dashboard
            </button>
          )}
        </div>
      )}

      {files.length > 0 && (
        <div className="dashboard-section">
          <h3>My Files</h3>
          <div className="file-grid">
            {files.map(f => (
              <div key={f.upload_id} className="file-card">
                <div className="file-info">
                  <FileIcon size={20} className="file-icon" />
                  <div className="file-details">
                    <span className="file-name">{f.filename}</span>
                    <span className="file-size">{(f.total_size / 1024 / 1024).toFixed(2)} MB</span>
                  </div>
                </div>
                <div className="file-actions">
                  <button onClick={() => handleDownloadFile(f.upload_id)} title="Download">
                    <Download size={16} />
                  </button>
                  <button onClick={() => handleShareFile(f.upload_id)} title="Share">
                    <Share2 size={16} />
                  </button>
                  <button onClick={() => handleDeleteFile(f.upload_id)} title="Delete" className="btn-delete">
                    <AlertCircle size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          {dashboardShareUrl && (
            <div className="share-box" style={{ marginTop: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Public Share Link (expires in 24h)</p>
                <button onClick={() => setDashboardShareUrl(null)} style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: '1rem' }}>✕</button>
              </div>
              <div className="share-input-group">
                <input readOnly value={dashboardShareUrl} />
                <button onClick={() => { navigator.clipboard.writeText(dashboardShareUrl); alert('Copied!'); }} title="Copy">
                  <Copy size={16} />
                </button>
                <a href={dashboardShareUrl} target="_blank" rel="noreferrer" title="Open">
                  <ExternalLink size={16} />
                </a>
              </div>
            </div>
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
