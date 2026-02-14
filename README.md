BackTestQ — repo overview and developer guide
============================================

This repository is a full-stack backtesting platform for equities (NSE). It includes:

- Frontend: Next.js app (React) that provides UI for Strategies, Runs and Portfolios.
- Backend API: FastAPI service that exposes REST endpoints for CRUD, run outputs and dashboards.
- Worker: Python worker that polls the DB for queued runs and executes backtests.
- Engine: Rust simulation engine (PyO3) used by the worker for fast execution.
- Database: Postgres stores market data, strategies, runs and results.
- Tools: small CLI adapters for ingesting market data (Yahoo, CSVs).

Architecture (high-level)
-------------------------

User -> Frontend (Next.js)
  - creates/edits strategies
  - creates runs (single symbol or portfolio_id)
  - views run details, equity, fills, metrics
  - manages portfolios

Backend API (FastAPI)
  - /strategies, /runs, /symbols, /portfolios
  - returns run outputs (equity, fills, metrics)
  - pagination + filters for runs

Worker (Python)
  - Polls runs table, claims QUEUED runs
  - Loads bars_daily for tickers and drives Rust engine
  - Compiles & runs user Python strategy (ctx API)
  - Persists run_equity, run_fills, run_metrics, run_logs

Engine (Rust via PyO3)
  - Provides Engine API: on_bar, place_market_order, process_fills_for_date, end_of_day, equity_curve, fills, metrics
  - Computes metrics: sharpe, annual return, volatility, max drawdown (paise & %)

Database (Postgres)
  - symbols, bars_daily (market data)
  - strategies, runs, run_equity, run_fills, run_metrics, run_logs
  - portfolios + portfolio_symbols

Market data adapters
  - tools/adapter_yahoo.py — uses yfinance (recommended for NSE)
  - tools/adapter_alphavantage.py — AlphaVantage adapter (AV limits / premium)
  - tools/market_adapter.py — CSV directory loader
  - tools/fetch_nifty50_tickers.py — helper to pull NIFTY 50 constituents (Wikipedia)

Local development — quickstart
------------------------------
Prereqs:
  - Docker & docker-compose (for Postgres), or a running Postgres database
  - Python 3.12 venv for backend & worker
  - Rust toolchain + maturin (for building PyO3 engine)

1) Start Postgres (docker-compose)
   docker-compose up -d db

2) Backend virtualenv (example)
   python -m venv backend/api/.venv
   source backend/api/.venv/bin/activate
   pip install -r backend/api/requirements.txt

3) Apply DB migrations
   cd backend/api
   .venv/bin/alembic upgrade head

4) Build & install Rust engine into the backend venv
   # make sure the venv you run this from is the same used by the worker/backend
   source backend/api/.venv/bin/activate
   pip install --upgrade maturin
   cd engine
   export PYO3_PYTHON="$(which python)"
   python -m maturin develop --release -i "$(which python)"

5) Start backend & worker
   # backend
   backend/api/.venv/bin/uvicorn trading_api.app.main:app --host 127.0.0.1 --port 8000 --reload &
   # worker
   backend/api/.venv/bin/python worker/trading_worker/worker.py &

6) Start frontend (Next.js)
   cd frontend
   npm install
   npm run dev

7) Ingest market data (example using Yahoo adapter)
   pip install yfinance
   python tools/fetch_nifty50_tickers.py    # creates data/nifty50_tickers.txt
   python tools/adapter_yahoo.py --tickers-file data/nifty50_tickers.txt

Notes and troubleshooting
-------------------------
- Engine build/link errors: always build/install the PyO3 wheel with maturin from the same Python venv the worker uses.
- Alembic migration errors: ensure DATABASE_URL points to the running Postgres and run alembic from backend/api.
— use Yahoo adapter for NSE.
- Recomputing metrics: the worker stores metrics for new runs. If you change metric logic you can add a script to recompute metrics from `run_equity`.
- UI tips: Runs page supports server-side pagination and filters; portfolio UI supports create/edit/delete.

Where to look in code
----------------------
- Frontend: frontend/src/app/
- Backend API: backend/api/src/trading_api/app/main.py and routes/
- Worker: worker/trading_worker/worker.py
- Engine: engine/src/lib.rs
- Data tools: tools/

Local Setup
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




