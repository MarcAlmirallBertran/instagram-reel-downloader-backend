# Instagram Reel Downloader Backend

FastAPI backend that downloads Instagram reels, extracts audio, and transcribes them using OpenAI Whisper.

## Features

- Download Instagram reels by URL
- Extract audio from downloaded videos (ffmpeg + pydub)
- Transcribe audio and extract topics (OpenAI Whisper + GPT-4o-mini)
- Download all task files as a ZIP archive
- Async task pipeline via Taskiq + Redis
- JWT authentication with per-user Fernet-encrypted credentials
- Docker Compose for one-command setup

## Prerequisites

- Python >= 3.11 (local dev)
- ffmpeg (system-level, required for audio extraction)
- PostgreSQL
- Redis
- An OpenAI API key (configured per user via `PATCH /users/me`)

## Quick start

### With Docker (recommended)

```bash
# Generate a Fernet encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set required env vars (or put them in a .env file)
export ENCRYPTION_KEY=<generated-key>
export JWT_SECRET_KEY=<your-secret>     # optional, has a default
export OPENAI_API_KEY=<your-key>        # optional, can be set per user

# Start all services (API, worker, PostgreSQL, Redis)
docker compose up --build
```

API is available at `http://localhost:8000`.

### Without Docker (local dev)

```bash
# Install dependencies
uv sync

# Start Redis and PostgreSQL separately, then run in two terminals:
uv run fastapi dev app/main.py              # API server (hot reload)
uv run taskiq worker app.broker:broker      # Task worker
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ENCRYPTION_KEY` | **required** | Fernet key for encrypting user secrets at rest. Generate with `Fernet.generate_key()`. |
| `JWT_SECRET_KEY` | `dev-secret-change-in-production` | Signs/verifies JWT tokens. Change in production. |
| `DATABASE_URL` | `postgresql://postgres:1234@localhost:5432/postgres` | PostgreSQL connection string. |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string (used by Taskiq broker). |
| `OPENAI_API_KEY` | — | Not used at runtime. Each user must configure their own key via `PATCH /users/me`. |
| `MEDIA_DIR` | `{tempdir}/reels` (local) / `/data/reels` (Docker) | Directory where downloaded media files are stored. |

## API overview

### Auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/users` | Register a new user |
| `POST` | `/users/login` | Login — returns a 24h JWT |
| `GET` | `/users/me` | Get profile (never returns raw secrets, only presence flags) |
| `PATCH` | `/users/me` | Update credentials (OpenAI key, Instagram username/password); send `""` to clear a field |

### Tasks (all require `Authorization: Bearer <token>`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/tasks` | Create a new task from an Instagram reel URL |
| `GET` | `/tasks` | List tasks. Optional query params: `status`, `sort_by` (`created_at`\|`updated_at`), `sort_order` (`asc`\|`desc`) |
| `GET` | `/tasks/{id}` | Get task detail and current status |
| `GET` | `/tasks/{id}/video` | Stream the downloaded video file |
| `GET` | `/tasks/{id}/audio` | Stream the extracted audio file |
| `GET` | `/tasks/{id}/transcript` | Get the transcript and extracted topics |
| `GET` | `/tasks/{id}/files` | Download all task files as a ZIP archive |
| `POST` | `/tasks/{id}/cancel` | Cancel a pending or in-progress task |

## Task pipeline

Each task runs through three chained steps:

```
pending → in_progress   (download starts)
        → processing    (audio extraction starts)
        → completed     (transcription done)
        → failed        (any step raises an error)
        → cancelled     (cancel endpoint called; in-flight steps finish then status is overridden)
```

1. **Download** — fetches the reel via `instaloader`; uses Instagram credentials if configured, otherwise anonymous.
2. **Audio extraction** — extracts audio from the video using pydub/ffmpeg.
3. **Transcription** — calls OpenAI Whisper for transcription, then GPT-4o-mini for topic extraction (non-fatal; topics stored as `null` on failure).

## Testing

```bash
uv run pytest
```

Tests use an SQLite in-memory database and an in-process task broker — no external services needed. To run a specific file or test:

```bash
uv run pytest test/api/routes/test_tasks.py
uv run pytest -k test_download_reel_ok
```

## Tech stack

- **API**: FastAPI, SQLModel, PostgreSQL
- **Tasks**: Taskiq, Redis
- **Download**: instaloader
- **Audio**: pydub, ffmpeg
- **Transcription**: OpenAI Whisper (`whisper-1`), GPT-4o-mini
- **Auth**: bcrypt, JWT (PyJWT), Fernet (cryptography)
