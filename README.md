<div align="center">

# ☁️ myCloud

**A production-grade, self-hosted cloud storage platform**

Resumable chunked uploads · Real-time progress · Secure sharing · Rate limiting

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

</div>

---

## Overview

myCloud is a self-hosted cloud storage platform that lets you upload, manage, download, and share files from any browser. It's designed with production-grade engineering principles: resumable uploads, real-time progress via Server-Sent Events, and per-user storage quotas, all running in Docker containers.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (React)                          │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  Upload   │  │  Progress  │  │  File    │  │    Share     │  │
│  │  Manager  │  │   (SSE)    │  │  Grid    │  │    Modal     │  │
│  └────┬─────┘  └─────┬──────┘  └────┬─────┘  └──────┬───────┘  │
│       │              │              │               │           │
└───────┼──────────────┼──────────────┼───────────────┼───────────┘
        │   HTTP/REST  │  EventSource │    HTTP/REST  │
        ▼              ▼              ▼               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (:8000)                       │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  Auth Router │  │Upload Router │  │   Rate Limiter       │   │
│  │  /auth/*     │  │  /uploads/*  │  │  (Token Bucket/Lua)  │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                     │               │
│  ┌──────┴───────┐  ┌──────┴───────────────────┐ │               │
│  │ Auth Service │  │    Service Layer          │ │               │
│  │              │  │ ┌────────────────────────┐│ │               │
│  │ • JWT Token  │  │ │   Upload Service       ││ │               │
│  │ • bcrypt     │  │ │   Download Service     ││ │               │
│  │ • OAuth2     │  │ │   Share Service        ││ │               │
│  └──────────────┘  │ │   File Service         ││ │               │
│                    │ └────────────────────────┘│ │               │
│                    └───────────┬───────────────┘ │               │
│                                │                 │               │
│  ┌─────────────────────────────┴─────────────────┴───────────┐  │
│  │              Pydantic Schemas / Config Layer               │  │
│  │         (Input validation, env-driven secrets)             │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────┬──────────────────────────────┬─────────────────────┘
             │                              │
     ┌───────▼───────┐             ┌────────▼────────┐
     │  PostgreSQL   │             │     Redis       │
     │    (:5432)    │             │    (:6379)      │
     │               │             │                 │
     │ • Users       │             │ • SSE Pub/Sub   │
     │ • Uploads     │             │ • Rate Limiting │
     │ • Chunks      │             │   (Token Bucket)│
     │ • Share Links │             │                 │
     │ • DL Tokens   │             │                 │
     └───────────────┘             └─────────────────┘
```

---

## Features

| Feature | Description |
|:---|:---|
| **Resumable Chunked Uploads** | Files are split into 5 MB chunks with SHA-256 integrity verification. If a transfer fails, it resumes from the last successful chunk, not from scratch. |
| **Real-Time Progress** | Server-Sent Events (SSE) via Redis pub/sub stream upload progress to the browser instantly. |
| **Pause / Resume / Cancel** | Full control over active uploads from the UI. |
| **Secure File Sharing** | Generate time-limited share links with optional download caps. |
| **Per-User Storage Quotas** | Configurable storage cap (default: 5 GB) enforced at upload initiation. |
| **Rate Limiting** | Redis-backed token bucket algorithm (Lua script) prevents abuse. |
| **Multi-Tenant** | Full user isolation: JWT authentication with bcrypt password hashing. |
| **Production-Grade Config** | All secrets loaded from environment variables via Pydantic Settings. App crashes on startup if secrets are missing. |

---

## Tech Stack

| Layer | Technology |
|:---|:---|
| **Frontend** | React 18, TypeScript, Vite, Lucide Icons |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy 2.0 (Async), Pydantic v2 |
| **Database** | PostgreSQL 15 (via asyncpg) |
| **Cache / Pub-Sub** | Redis 7 (SSE broadcasting + rate limiting) |
| **Auth** | JWT (python-jose) + bcrypt |
| **Migrations** | Alembic |
| **Infrastructure** | Docker, Docker Compose |

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed

### 1. Clone the repository

```bash
git clone https://github.com/CapedCrusader03/myCloud.git
cd myCloud
```

### 2. Configure environment variables

```bash
cp .env.example backend/.env
```

Open `backend/.env` and **change the secret keys** to random strings:

```env
AUTH_SECRET_KEY=<your-random-64-char-hex-string>
DOWNLOAD_TOKEN_SECRET_KEY=<your-different-random-64-char-hex-string>
```

> **Tip:** Generate secure keys with: `openssl rand -hex 32`

### 3. Start the application

```bash
docker compose up -d --build
```

This starts 4 containers:

| Service | URL | Purpose |
|:---|:---|:---|
| **Frontend** | [http://localhost:5173](http://localhost:5173) | React dashboard |
| **API** | [http://localhost:8000](http://localhost:8000) | FastAPI backend |
| **PostgreSQL** | `localhost:5432` | Primary database |
| **Redis** | `localhost:6379` | Pub/Sub + rate limiting |

### 4. Run database migrations

```bash
docker compose exec api alembic upgrade head
```

### 5. Open the app

Navigate to **[http://localhost:5173](http://localhost:5173)**, create an account, and start uploading!

---

## Configuration

All configuration is done through environment variables in `backend/.env`:

| Variable | Required | Default | Description |
|:---|:---|:---|:---|
| `AUTH_SECRET_KEY` | ✅ | — | JWT secret for authentication |
| `DOWNLOAD_TOKEN_SECRET_KEY` | ✅ | — | JWT secret for download tokens |
| `DATABASE_URL` | ❌ | `postgresql+asyncpg://...@db:5432/mycloud` | PostgreSQL connection string |
| `REDIS_URL` | ❌ | `redis://redis:6379/0` | Redis connection string |
| `CORS_ORIGINS` | ❌ | `http://localhost:5173` | Comma-separated allowed origins |
| `MAX_STORAGE_BYTES` | ❌ | `5368709120` (5 GB) | Per-user storage quota |
| `RATE_LIMIT_CAPACITY` | ❌ | `10` | Token bucket burst capacity |
| `RATE_LIMIT_REFILL_RATE` | ❌ | `5` | Tokens refilled per second |

---

## Project Structure

```
myCloud/
├── backend/
│   ├── api/
│   │   ├── auth.py              # Auth routes (login, register)
│   │   └── uploads.py           # Upload, download, share, SSE routes
│   ├── models/
│   │   └── domain.py            # SQLAlchemy models (User, Upload, Chunk, ...)
│   ├── services/
│   │   ├── auth_service.py      # JWT, bcrypt, user lookup
│   │   ├── upload_service.py    # Upload orchestration & chunk processing
│   │   ├── download_service.py  # Download token generation & validation
│   │   ├── share_service.py     # Share link CRUD
│   │   ├── file_service.py      # File listing & deletion
│   │   ├── storage_service.py   # Physical file I/O (chunks, assembly)
│   │   └── worker.py            # Background cleanup of stale uploads
│   ├── migrations/              # Alembic migrations
│   ├── config.py                # Pydantic Settings (env-driven config)
│   ├── schemas.py               # Request/response validation schemas
│   ├── database.py              # Async SQLAlchemy engine & session
│   ├── middleware.py             # Redis token-bucket rate limiter
│   ├── main.py                  # FastAPI app entry point
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Main application component
│   │   └── index.css            # Google Drive-style design system
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Security

- **No hardcoded secrets**: all secrets are loaded from environment variables; the app refuses to start if they're missing
- **CORS whitelist**: no wildcard origins
- **Cryptographic slugs**: share links use `secrets.token_urlsafe()`, not `random.choice()`
- **Input validation**: Pydantic schemas enforce filename sanitization, SHA-256 hex format, and bounded ranges
- **Rate limiting**: Redis-backed token bucket on upload and auth endpoints
- **Non-root Docker**: production container runs as unprivileged `appuser`
- **DB-level constraints**: Unique constraint on `(upload_id, chunk_index)` prevents duplicate chunks

---

## Previous Version

The original project documentation can be found in the [Legacy README](README_LEGACY.md).

## License

This project is open source and available under the [MIT License](LICENSE).
```