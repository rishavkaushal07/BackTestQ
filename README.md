# BackTestQ
This project involves complete end to end strategy bactesting engine.

Full-stack backtesting system:
- FastAPI backend (strategies, runs, portfolios, market data)
- Worker (pulls queued runs, executes backtests, writes results)
- Next.js dashboard (create runs, view results)
- Postgres database (Docker)

## Prereqs
- Python 3.12 (recommended)
- Node 18+ (or 20+)
- Docker Desktop

## 1) Start Postgres (Docker)
```bash
cp .env.example .env
docker compose up -d
docker exec -it backtestq-postgres psql -U backtestq -d trading_sim -c "select 1;"

## 2) Backend API
     cd backend/api
     python -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt

     alembic upgrade head

     python -m uvicorn trading_api.app.main:app --reload --port 8000

## 3) Worker
    cd worker
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

    python -m trading_worker.worker

## 4) Frontend
    cd frontend
    npm install
    npm run dev




