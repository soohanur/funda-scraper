# Data Info Backend

FastAPI backend for the Data Info automation platform.

## API Endpoints
- `POST /api/v1/auth/register` — Register user
- `POST /api/v1/auth/login` — Login (JWT token)
- `POST /api/v1/funda/start` — Start Funda scraper
- `GET /api/v1/funda/status` — Scraper status
- `POST /api/v1/funda/stop` — Stop scraper
- `GET /api/v1/system/health` — Health check

## Setup
```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
