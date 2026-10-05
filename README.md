# Exploding Kittens Lite

Current local stack:

- `backend`: FastAPI + Socket.IO
- `db`: PostgreSQL
- `frontend`: Next.js + TypeScript realtime test harness

## Run with Docker Compose

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

## Services

- Backend health: `http://127.0.0.1:8000/health`
- PostgreSQL: `postgresql://postgres:postgres@127.0.0.1:5432/boardgame`
- Frontend: `http://127.0.0.1:3000`

## Frontend

See [frontend/README.md](frontend/README.md) for setup, socket/session APIs,
reconnect and takeover behavior, and browser smoke tests. It runs with the root
Docker Compose stack at `http://localhost:3000`.
This is the realtime verification page; lobby/game product screens come later.
