# Backend

Python backend skeleton for the Exploding Kittens Lite realtime service.

## Stack

- Python 3.12+
- FastAPI
- python-socketio
- Pydantic Settings
- Uvicorn

## Local run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Local tests

Use Python 3.12+ from the repository root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

If the virtual environment already exists, activate it and install the dev
extras before running tests. The suite uses in-memory registries and mocked
Socket.IO emissions; PostgreSQL and a running server are not required.

See [the test coverage map](../plan/detail-implementation/15-backend-test-coverage.md)
for covered rules, regression fixes, and deferred integration work.

## Docker Compose run

From repo root:

```bash
cp backend/.env.example backend/.env
docker compose up --build backend db
```

Backend will be available at `http://127.0.0.1:8000` and PostgreSQL at `127.0.0.1:5432`.

To stop:

```bash
docker compose down
```

## Docker Compose test

From repo root:

```bash
docker compose run --rm backend pytest
```

`APP_CORS_ORIGINS` uses JSON array format in `.env`, for example:

```env
APP_CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

## Smoke check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"exploding-kittens-backend","environment":"development"}
```

## Current structure

- `app/api`: HTTP routes
- `app/core`: config and shared application primitives
- `app/realtime`: Socket.IO bootstrap and events
- `app/modules/room`: room domain module placeholder
- `app/modules/session`: session domain module placeholder
- `app/modules/game`: game domain module placeholder
