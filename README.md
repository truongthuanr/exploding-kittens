# Exploding Kittens Lite

Current local stack:

- `backend`: FastAPI + Socket.IO
- `db`: PostgreSQL

## Run with Docker Compose

```bash
cp backend/.env.example backend/.env
docker compose up --build backend db
```

## Services

- Backend health: `http://127.0.0.1:8000/health`
- PostgreSQL: `postgresql://postgres:postgres@127.0.0.1:5432/boardgame`

Frontend will be added in a separate issue.
