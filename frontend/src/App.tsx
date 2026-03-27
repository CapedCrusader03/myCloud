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
  Search,
  HardDrive,
  Trash2,
  X,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const CHUNK_SIZE = 5 * 1024 * 1024;

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

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<UploadState | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [dashboardShareUrl, setDashboardShareUrl] = useState<string | null>(null);
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [searchQ, setSearchQ] = useState('');

  // Auth
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [email, setEmail] = useState<string>(localStorage.getItem('userEmail') || '');
  const [authView, setAuthView] = useState<'login' | 'register'>('login');
  const [password, setPassword] = useState('');

  // Share-link route intercept
  useEffect(() => {
    const path = window.location.pathname;
    if (path.startsWith('/s/')) window.location.replace(`${API_BASE}${path}`);
  }, []);

  // Axios auth header
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

  // SSE progress updates
  useEffect(() => {
    if (!upload?.id || upload.status === 'complete' || upload.status === 'error') return;
    const es = new EventSource(`${API_BASE}/uploads/${upload.id}/events`);
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      setUpload(prev => {
        if (!prev) return null;
        return {
          ...prev,
          status: data.status ?? prev.status,
          percent: data.percent ?? prev.percent,
          receivedChunks: Array.isArray(data.received_chunks) ? data.received_chunks.length : (data.received_chunks ?? prev.receivedChunks),
          totalChunks: data.total_chunks ?? prev.totalChunks,
        };
      });
      if (data.status === 'complete') { es.close(); fetchFiles(); }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [upload?.id, upload?.status]);

  // Fetch file list
  const fetchFiles = async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/uploads`);
      setFiles(data);
    } catch { /* silently ignore */ }
  };

  useEffect(() => {
    if (token) {
      fetchFiles();
      const id = setInterval(fetchFiles, 10000);
      return () => clearInterval(id);
    }
  }, [token]);

  // Auth
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
        alert('Account created! Please login.');
        setAuthView('login');
      }
    } catch {
      alert('Authentication failed. Check credentials.');
    }
  };

  const handleLogout = () => { setToken(null); setFiles([]); setUpload(null); };

  // Upload
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setFile(e.target.files[0]);
  };

  const calculateChecksum = async (f: File) => {
    const buf = await f.arrayBuffer();
    const hash = await crypto.subtle.digest('SHA-256', buf);
    return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('');
  };

  const startUpload = async () => {
    if (!file) return;
    try {
      const checksum = await calculateChecksum(file);
      const { data: init } = await axios.post(`${API_BASE}/uploads`, {
        filename: file.name,
        total_size: file.size,
        chunk_size: CHUNK_SIZE,
        file_checksum: checksum,
      });
      const uploadId = init.upload_id;
      const headResp = await axios.head(`${API_BASE}/uploads/${uploadId}`);
      const missing = headResp.headers['x-missing-chunks']
        ? headResp.headers['x-missing-chunks'].split(',').map(Number)
        : null;

      setUpload({ id: uploadId, filename: file.name, percent: 0, status: 'uploading', totalChunks: Math.ceil(file.size / CHUNK_SIZE), receivedChunks: 0 });
      await uploadChunks(file, uploadId, missing);
    } catch {
      alert('Upload failed. Try again.');
    }
  };

  const uploadChunks = async (f: File, uploadId: string, missingArray: number[] | null) => {
    const totalChunks = Math.ceil(f.size / CHUNK_SIZE);
    for (let i = 0; i < totalChunks; i++) {
      if (missingArray && !missingArray.includes(i)) continue;
      const start = i * CHUNK_SIZE;
      const chunk = f.slice(start, Math.min(start + CHUNK_SIZE, f.size));

      let attempt = 0;
      const MAX_RETRIES = 5;

      while (attempt <= MAX_RETRIES) {
        try {
          await axios.patch(`${API_BASE}/uploads/${uploadId}/chunks/${i}`, chunk, {
            headers: { 'Content-Type': 'application/octet-stream' },
          });
          break; // success — move to next chunk
        } catch (err: any) {
          const status = err?.response?.status;
          attempt++;
          if (attempt > MAX_RETRIES) {
            console.error(`Chunk ${i} failed after ${MAX_RETRIES} retries.`);
            return; // give up on this upload
          }
          // Respect Retry-After for 429, otherwise exponential backoff
          const retryAfterHeader = err?.response?.headers?.['retry-after'];
          const waitMs = status === 429 && retryAfterHeader
            ? parseInt(retryAfterHeader) * 1000
            : Math.min(1000 * 2 ** attempt, 30_000); // 2s, 4s, 8s… capped at 30s
          console.warn(`Chunk ${i} failed (${status}), retrying in ${waitMs}ms (attempt ${attempt}/${MAX_RETRIES})…`);
          await new Promise(res => setTimeout(res, waitMs));
        }
      }
    }
  };

  // File actions
  const handleDownloadFile = async (id: string) => {
    try {
      const { data } = await axios.get(`${API_BASE}/uploads/${id}/token`);
      window.open(`${API_BASE}/uploads/download/${data.token}`, '_blank');
    } catch { alert('Download failed.'); }
  };

  const handleShareFile = async (id: string) => {
    try {
      const { data } = await axios.post(`${API_BASE}/uploads/${id}/share`, { ttl_hours: 24 });
      setDashboardShareUrl(`${window.location.origin}${data.share_url}`);
    } catch { alert('Failed to share.'); }
  };

  const handleDeleteFile = async (id: string) => {
    if (!confirm('Permanently delete this file?')) return;
    try { await axios.delete(`${API_BASE}/uploads/${id}`); fetchFiles(); }
    catch { alert('Delete failed.'); }
  };

  const handleDownload = async () => {
    if (!upload?.id) return;
    try {
      const { data } = await axios.get(`${API_BASE}/uploads/${upload.id}/token`);
      window.open(`${API_BASE}/uploads/download/${data.token}`, '_blank');
    } catch { alert('Failed to get download token.'); }
  };

  const handleShare = async () => {
    if (!upload?.id) return;
    try {
      const { data } = await axios.post(`${API_BASE}/uploads/${upload.id}/share`, { ttl_hours: 24 });
      setShareUrl(`${window.location.origin}${data.share_url}`);
    } catch { alert('Failed to create share link.'); }
  };

  const filtered = files.filter(f => f.filename.toLowerCase().includes(searchQ.toLowerCase()));

  // ── Auth screen ──────────────────────────────────────────────────────────
  if (!token) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <div className="auth-logo">
            <div className="auth-logo-icon">m</div>
            <h1>my<span>Cloud</span></h1>
          </div>
          <p className="auth-subtitle">
            {authView === 'login' ? 'Sign in to your drive' : 'Create a new account'}
          </p>
          <form onSubmit={handleAuth}>
            <input className="auth-field" type="email" placeholder="Email address" value={email} onChange={e => setEmail(e.target.value)} required />
            <input className="auth-field" type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required />
            <button className="btn-auth" type="submit">
              {authView === 'login' ? <><LogIn size={16} /> Sign In</> : <><UserPlus size={16} /> Create Account</>}
            </button>
          </form>
          <p className="auth-switch">
            {authView === 'login' ? <>Don't have an account? <a onClick={() => setAuthView('register')}>Register</a></> : <>Already have an account? <a onClick={() => setAuthView('login')}>Sign in</a></>}
          </p>
        </div>
      </div>
    );
  }

  // ── Main app ─────────────────────────────────────────────────────────────
  const avatarLetter = email.charAt(0).toUpperCase();
  const statusChip = upload ? `chip-${upload.status}` : '';

  return (
    <>
      {/* Header */}
      <header className="app-header">
        <div className="header-logo">
          <div className="header-logo-icon">m</div>
          <span className="header-logo-text">my<span style={{ color: 'var(--blue)' }}>Cloud</span></span>
        </div>

        <div className="header-search">
          <Search size={18} />
          <input placeholder="Search in Drive" value={searchQ} onChange={e => setSearchQ(e.target.value)} />
        </div>

        <div className="header-actions">
          <span className="user-email-label">{email}</span>
          <div className="user-avatar" title={email}>{avatarLetter}</div>
          <button className="icon-btn" onClick={handleLogout} title="Sign out"><LogOut size={18} /></button>
        </div>
      </header>

      <div className="app-shell">
        {/* Sidebar */}
        <aside className="app-sidebar">
          <button className="btn-new" onClick={() => document.getElementById('file-input')?.click()}>
            <UploadIcon size={20} color="var(--blue)" />
            New Upload
          </button>
          <input type="file" id="file-input" hidden onChange={handleFileChange} />

          <button className="sidebar-link active">
            <HardDrive size={18} /> My Drive
          </button>

          <div className="sidebar-divider" />

          <div className="storage-info">
            <p className="storage-text"><strong>{formatBytes(files.reduce((a, f) => a + f.total_size, 0))}</strong> used</p>
            <div className="storage-bar-track">
              <div className="storage-bar-fill" style={{ width: `${Math.min(100, (files.reduce((a, f) => a + f.total_size, 0) / (5 * 1024 * 1024 * 1024)) * 100).toFixed(1)}%` }} />
            </div>
            <p className="storage-text">of 5 GB</p>
          </div>
        </aside>

        {/* Main */}
        <main className="app-main">

          {/* Active upload area */}
          {!upload ? (
            file ? (
              <div className="upload-progress-card" style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
                <FileIcon size={32} color="var(--blue)" style={{ flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p className="upload-progress-name">{file.name}</p>
                  <p className="upload-progress-subtitle">{formatBytes(file.size)} — ready to upload</p>
                </div>
                <button className="btn-primary" onClick={startUpload}><UploadIcon size={16} /> Start Upload</button>
                <button className="btn-text" onClick={() => setFile(null)}><X size={16} /></button>
              </div>
            ) : (
              <div
                className={`upload-zone ${dragActive ? 'dragging' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={e => { e.preventDefault(); setDragActive(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); }}
                onClick={() => document.getElementById('file-input')?.click()}
              >
                <div className="upload-zone-icon"><UploadIcon size={40} /></div>
                <h3>Drop files here or click to browse</h3>
                <p>Supports all file types · Max 5 GB per file</p>
              </div>
            )
          ) : (
            <div className="upload-progress-card" style={{ marginBottom: '1.5rem' }}>
              <div className="upload-progress-header">
                <FileIcon size={24} color="var(--blue)" />
                <div>
                  <p className="upload-progress-name">{upload.filename}</p>
                  <p className="upload-progress-subtitle">{upload.percent.toFixed(1)}% complete</p>
                </div>
                <span className={`upload-status-chip ${statusChip}`}>
                  {upload.status === 'uploading' && <><Loader2 size={12} className="spin" /> Uploading</>}
                  {upload.status === 'assembling' && 'Assembling'}
                  {upload.status === 'complete' && <><CheckCircle size={12} /> Complete</>}
                  {upload.status === 'error' && <><AlertCircle size={12} /> Error</>}
                </span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${upload.percent}%` }} />
              </div>
              <div className="upload-actions">
                {upload.status === 'complete' && (
                  <>
                    <button className="btn-primary" onClick={handleDownload}><Download size={14} /> Download</button>
                    <button className="btn-secondary" onClick={handleShare}><Share2 size={14} /> Share</button>
                    <button className="btn-text" onClick={() => { setUpload(null); setFile(null); setShareUrl(null); fetchFiles(); }}>← Back to Drive</button>
                  </>
                )}
              </div>
              {shareUrl && (
                <div className="share-popup" style={{ marginTop: '1rem' }}>
                  <div className="share-popup-header">
                    <span className="share-popup-title">Share link (24h)</span>
                    <button className="icon-btn" onClick={() => setShareUrl(null)}><X size={14} /></button>
                  </div>
                  <div className="share-link-row">
                    <input className="share-link-input" readOnly value={shareUrl} />
                    <button className="btn-secondary" onClick={() => { navigator.clipboard.writeText(shareUrl!); }}><Copy size={14} /></button>
                    <a className="btn-secondary" href={shareUrl} target="_blank" rel="noreferrer"><ExternalLink size={14} /></a>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* File grid */}
          <div className="main-toolbar">
            <h2 className="main-title">My Drive</h2>
          </div>

          {dashboardShareUrl && (
            <div className="share-popup" style={{ marginBottom: '1.25rem' }}>
              <div className="share-popup-header">
                <span className="share-popup-title">Share link (expires in 24h)</span>
                <button className="icon-btn" onClick={() => setDashboardShareUrl(null)}><X size={14} /></button>
              </div>
              <div className="share-link-row">
                <input className="share-link-input" readOnly value={dashboardShareUrl} />
                <button className="btn-secondary" onClick={() => { navigator.clipboard.writeText(dashboardShareUrl!); alert('Copied!'); }}><Copy size={14} /></button>
                <a className="btn-secondary" href={dashboardShareUrl} target="_blank" rel="noreferrer"><ExternalLink size={14} /></a>
              </div>
            </div>
          )}

          {filtered.length === 0 ? (
            <div className="empty-state">
              <HardDrive size={56} color="var(--gray-200)" />
              <h3>{searchQ ? 'No files match your search' : 'Your drive is empty'}</h3>
              <p>{searchQ ? 'Try a different search term' : 'Use the "New Upload" button to get started'}</p>
            </div>
          ) : (
            <>
              <p className="section-title">Files — {filtered.length} item{filtered.length !== 1 ? 's' : ''}</p>
              <div className="file-grid">
                {filtered.map(f => (
                  <div key={f.upload_id} className="file-card">
                    <div className="file-card-thumb">
                      <FileIcon size={40} />
                    </div>
                    <div className="file-card-body">
                      <p className="file-card-name" title={f.filename}>{f.filename}</p>
                      <p className="file-card-meta">{formatBytes(f.total_size)}</p>
                      <p className="file-card-meta">{formatDate(f.created_at)}</p>
                    </div>
                    <div className="file-card-actions">
                      <button className="file-action-btn" onClick={() => handleDownloadFile(f.upload_id)} title="Download"><Download size={15} /></button>
                      <button className="file-action-btn" onClick={() => handleShareFile(f.upload_id)} title="Share"><Share2 size={15} /></button>
                      <button className="file-action-btn delete" onClick={() => handleDeleteFile(f.upload_id)} title="Delete"><Trash2 size={15} /></button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </main>
      </div>
    </>
  );
}
