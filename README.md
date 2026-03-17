# Instagram Reel Downloader Backend

A FastAPI backend that turns an Instagram reel URL into a downloadable video, extracted audio, and a full transcript with topics — all via an async pipeline.

## What does it do?

You give it an Instagram reel URL. It:

1. Downloads the video using your Instagram credentials (or anonymously if none are set).
2. Extracts the audio track from the video.
3. Transcribes the audio using OpenAI Whisper, then runs GPT-4o-mini to extract a list of topics.

Everything runs asynchronously — you submit a URL, get back a task ID, and poll for status or wait for completion. Once done, you can stream individual files (video, audio, transcript) or download everything as a ZIP.

## How it works

### User flow

1. **Register** — `POST /users` with email + password.
2. **Log in** — `POST /users/login` to get a 24h JWT bearer token.
3. **Add your OpenAI key** — `PATCH /users/me` with `{"openai_api_key": "sk-..."}`. Without this, the transcription step will fail. You can also add Instagram credentials here to avoid anonymous-download rate limits.
4. **Submit a reel** — `POST /tasks` with `{"uri": "https://www.instagram.com/reel/ABC123/"}`. You get back a `task_id`.
5. **Check status** — `GET /tasks/{task_id}` until status is `completed` (or `failed`/`cancelled`).
6. **Download files** — stream individual files or grab everything as a ZIP.

### Status transitions

```
pending → in_progress   (download starts)
        → processing    (audio extraction starts)
        → completed     (transcription done)
        → failed        (any step raises an unrecoverable error)
        → cancelled     (cancel endpoint called; any in-flight step finishes, then status is overridden)
```

A task moves through these three pipeline steps in sequence:

1. **Download** — fetches the reel via `instaloader`; uses Instagram credentials if configured, otherwise anonymous.
2. **Audio extraction** — pulls the audio track from the video using pydub + ffmpeg.
3. **Transcription** — calls OpenAI Whisper for transcription, then GPT-4o-mini for topic extraction. Topic extraction is non-fatal: if it fails, `topics` is stored as `null` and the task still completes.

## Prerequisites

- Python >= 3.11
- [`uv`](https://docs.astral.sh/uv/) (package manager)
- ffmpeg (system-level, required for audio extraction — `brew install ffmpeg` on macOS)
- PostgreSQL
- Redis (not needed for local development — see below)
- An OpenAI API key (configured per user, not globally)

## Quick start

### With Docker (recommended)

The simplest way to get everything running. Docker Compose starts the API server, the task worker, PostgreSQL, and Redis for you.

```bash
# Generate a Fernet encryption key (required)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set required env vars (or put them in a .env file)
export ENCRYPTION_KEY=<generated-key>
export JWT_SECRET_KEY=<your-secret>     # optional, has a default

# Start all services
docker compose up --build
```

API is available at `http://localhost:8000`.

### Without Docker (local dev)

This approach lets you run without Redis by setting `ENVIRONMENT=local`. In that mode, tasks run synchronously in-process (InMemoryBroker) instead of being dispatched to a worker — useful for development and debugging.

```bash
# 1. Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install dependencies
uv sync

# 3. Set up env vars (minimum required)
export ENCRYPTION_KEY=<generated-key>   # see Docker section above for how to generate
export ENVIRONMENT=local                # skips Redis; tasks run in-process

# 4. Start PostgreSQL (still required), then start the API server
uv run fastapi dev app/main.py
```

With `ENVIRONMENT=local`, you do **not** need to run a separate Taskiq worker — tasks execute inline when the API receives a request.

If you want to run with a real Redis worker (closer to production):

```bash
# Two terminals:
uv run fastapi dev app/main.py          # API server (hot reload)
uv run taskiq worker app.broker:broker  # Task worker
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ENCRYPTION_KEY` | **required** | Fernet key for encrypting user secrets at rest. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `JWT_SECRET_KEY` | `dev-secret-change-in-production` | Signs/verifies JWT tokens. Change in production. |
| `DATABASE_URL` | `postgresql://postgres:1234@localhost:5432/postgres` | PostgreSQL connection string. |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string (used by Taskiq broker). Not needed when `ENVIRONMENT=local`. |
| `ENVIRONMENT` | — | Set to `local` or `pytest` to use an in-process broker (no Redis required). |
| `OPENAI_API_KEY` | — | Not used at the server level. Each user configures their own key via `PATCH /users/me`. |
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
| `GET` | `/tasks` | List tasks. Optional: `status`, `sort_by` (`created_at`\|`updated_at`), `sort_order` (`asc`\|`desc`) |
| `GET` | `/tasks/{id}` | Get task detail, current status, and file metadata |
| `GET` | `/tasks/{id}/files/{file_type}` | Stream a single file. `file_type` is `video`, `audio`, or `transcript` |
| `GET` | `/tasks/{id}/files` | Download all task files as a ZIP archive |
| `POST` | `/tasks/{id}/cancel` | Cancel a pending or in-progress task (409 if already terminal) |

## Testing

```bash
uv run pytest
```

Tests use an SQLite in-memory database and an in-process task broker — no external services needed. To run a specific file or test:

```bash
uv run pytest test/api/routes/test_tasks.py
uv run pytest -k test_download_reel_ok
```

> **Note:** Always run the full suite (`uv run pytest`) rather than a single service test file in isolation. The test database is initialized by the module-scoped `client` fixture; running a single file may fail with "no such table".

## Tech stack

- **API**: FastAPI, SQLModel, PostgreSQL
- **Tasks**: Taskiq, Redis
- **Download**: instaloader
- **Audio**: pydub, ffmpeg
- **Transcription**: OpenAI Whisper (`whisper-1`), GPT-4o-mini
- **Auth**: bcrypt, JWT (PyJWT), Fernet (cryptography)
