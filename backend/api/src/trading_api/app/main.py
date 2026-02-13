from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from .config import settings
from .db import get_db
from . import models, schemas
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from .routes import portfolios

app = FastAPI(title="Trading Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolios.router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "api"}

# ---- Strategies ----
@app.post("/strategies", response_model=schemas.StrategyOut)
def create_strategy(payload: schemas.StrategyCreate, db: Session = Depends(get_db)):
    s = models.Strategy(name=payload.name, code=payload.code)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s

@app.get("/strategies", response_model=list[schemas.StrategyOut])
def list_strategies(db: Session = Depends(get_db)):
    return db.query(models.Strategy).order_by(models.Strategy.updated_at.desc()).all()

@app.get("/strategies/{strategy_id}", response_model=schemas.StrategyOut)
def get_strategy(strategy_id: UUID, db: Session = Depends(get_db)):
    s = db.get(models.Strategy, strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return s

@app.put("/strategies/{strategy_id}", response_model=schemas.StrategyOut)
def update_strategy(strategy_id: UUID, payload: schemas.StrategyUpdate, db: Session = Depends(get_db)):
    s = db.get(models.Strategy, strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail="Strategy not found")

    if payload.name is not None:
        s.name = payload.name
    if payload.code is not None:
        s.code = payload.code

    s.updated_at = datetime.utcnow()
    db.add(s)
    db.commit()
    db.refresh(s)
    return s

# ---- Runs ----
@app.post("/runs", response_model=schemas.RunOut)
def create_run(payload: schemas.RunCreate, db: Session = Depends(get_db)):
    strat = db.get(models.Strategy, payload.strategy_id)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")

    config = {
        "venue": "NSE",
        "timeframe": "1D",
        "symbols": payload.symbols,
        "portfolio_id": payload.portfolio_id,
        "weighting": "EQUAL",
        "rebalance": "ONCE_AT_START",
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
        "starting_cash_paise": payload.starting_cash_paise or settings.DEFAULT_STARTING_CASH_PAISE,
        "fee_bps": payload.fee_bps if payload.fee_bps is not None else settings.DEFAULT_FEE_BPS,
        "slippage_bps": payload.slippage_bps if payload.slippage_bps is not None else settings.DEFAULT_SLIPPAGE_BPS,
        "fill_rule": "NEXT_OPEN",
        "asset_class": "EQUITY",
        "currency": "INR",
    }

    r = models.Run(strategy_id=payload.strategy_id, status="QUEUED", config_json=config)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r

@app.get("/runs", response_model=list[schemas.RunOut])
def list_runs(db: Session = Depends(get_db)):
    return db.query(models.Run).order_by(models.Run.created_at.desc()).limit(200).all()

@app.get("/runs/{run_id}", response_model=schemas.RunOut)
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    r = db.get(models.Run, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")
    return r

# ---- Dashboard data ----

@app.get("/runs/{run_id}/equity", response_model=list[schemas.RunEquityPoint])
def get_run_equity(run_id: UUID, db: Session = Depends(get_db)):
    # Ensure run exists
    r = db.get(models.Run, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")

    rows = db.execute(
        text("""
            SELECT date, equity_paise
            FROM run_equity
            WHERE run_id = :run_id
            ORDER BY date ASC
        """),
        {"run_id": str(run_id)},
    ).fetchall()

    return [
        schemas.RunEquityPoint(
            date=row[0],
            equity_paise=int(row[1]),
            equity_inr=float(row[1]) / 100.0,
        )
        for row in rows
    ]


@app.get("/runs/{run_id}/fills", response_model=list[schemas.RunFillOut])
def get_run_fills(run_id: UUID, db: Session = Depends(get_db)):
    r = db.get(models.Run, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")

    rows = db.execute(
        text("""
            SELECT
              f.date,
              s.ticker,
              f.side,
              f.qty,
              f.price_paise,
              f.fee_paise,
              f.order_id
            FROM run_fills f
            JOIN symbols s ON s.id = f.symbol_id
            WHERE f.run_id = :run_id
            ORDER BY f.date ASC, f.order_id ASC
        """),
        {"run_id": str(run_id)},
    ).fetchall()

    out: list[schemas.RunFillOut] = []
    for (d, ticker, side, qty, px, fee, oid) in rows:
        out.append(
            schemas.RunFillOut(
                date=d,
                ticker=ticker,
                side=side,
                qty=int(qty),
                price_paise=int(px),
                price_inr=float(px) / 100.0,
                fee_paise=int(fee),
                fee_inr=float(fee) / 100.0,
                order_id=int(oid),
            )
        )
    return out


@app.get("/runs/{run_id}/metrics", response_model=schemas.RunMetricsOut)
def get_run_metrics(run_id: UUID, db: Session = Depends(get_db)):
    r = db.get(models.Run, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")

    row = db.execute(
        text("""
            SELECT sharpe, max_drawdown_paise, win_rate, trades_closed, realized_pnl_paise, fees_paise
            FROM run_metrics
            WHERE run_id = :run_id
            LIMIT 1
        """),
        {"run_id": str(run_id)},
    ).fetchone()

    # If run is still running or no metrics yet
    if not row:
        return schemas.RunMetricsOut(
            run_id=run_id,
            sharpe=0.0,
            max_drawdown_paise=0,
            max_drawdown_inr=0.0,
            win_rate=0.0,
            trades_closed=0,
            realized_pnl_paise=0,
            realized_pnl_inr=0.0,
            fees_paise=0,
            fees_inr=0.0,
        )

    sharpe, mdd, wr, tc, rp, fees = row
    return schemas.RunMetricsOut(
        run_id=run_id,
        sharpe=float(sharpe),
        max_drawdown_paise=int(mdd),
        max_drawdown_inr=float(mdd) / 100.0,
        win_rate=float(wr),
        trades_closed=int(tc),
        realized_pnl_paise=int(rp),
        realized_pnl_inr=float(rp) / 100.0,
        fees_paise=int(fees),
        fees_inr=float(fees) / 100.0,
    )


@app.get("/symbols", response_model=list[schemas.SymbolOut])
def list_symbols(db: Session = Depends(get_db)):
    return db.query(models.Symbol).filter(models.Symbol.is_active == True).order_by(models.Symbol.ticker.asc()).all()


@app.get("/symbols/{ticker}/bars", response_model=list[schemas.BarOut])
def get_symbol_bars(ticker: str, start: str, end: str, db: Session = Depends(get_db)):
    # start/end are 'YYYY-MM-DD'
    sym = db.query(models.Symbol).filter(models.Symbol.ticker == ticker, models.Symbol.is_active == True).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Symbol not found")

    rows = db.execute(
        text("""
            SELECT date, open_paise, high_paise, low_paise, close_paise, volume
            FROM bars_daily
            WHERE symbol_id = :sid
              AND date BETWEEN :start AND :end
            ORDER BY date ASC
        """),
        {"sid": str(sym.id), "start": start, "end": end},
    ).fetchall()

    return [
        schemas.BarOut(
            date=r[0],
            open_paise=int(r[1]),
            high_paise=int(r[2]),
            low_paise=int(r[3]),
            close_paise=int(r[4]),
            volume=int(r[5] or 0),
            open_inr=float(r[1]) / 100.0,
            high_inr=float(r[2]) / 100.0,
            low_inr=float(r[3]) / 100.0,
            close_inr=float(r[4]) / 100.0,
        )
        for r in rows
    ]
