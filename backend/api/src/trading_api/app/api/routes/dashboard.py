from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from trading_api.app.db import get_db  # adjust if your get_db path differs

router = APIRouter(prefix="", tags=["dashboard"])


@router.get("/runs")
def list_runs(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT id, strategy_id, status, created_at, started_at, finished_at, error, config_json
            FROM runs
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    row = db.execute(
        text("""
            SELECT id, strategy_id, status, created_at, started_at, finished_at, error, config_json
            FROM runs
            WHERE id = :id
        """),
        {"id": run_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    return dict(row)


@router.get("/runs/{run_id}/equity")
def get_run_equity(run_id: str, db: Session = Depends(get_db)):
    # ensure run exists (nice error)
    ok = db.execute(text("SELECT 1 FROM runs WHERE id=:id"), {"id": run_id}).scalar()
    if not ok:
        raise HTTPException(status_code=404, detail="run not found")

    rows = db.execute(
        text("""
            SELECT date, equity_paise
            FROM run_equity
            WHERE run_id = :id
            ORDER BY date ASC
        """),
        {"id": run_id},
    ).mappings().all()

    # return both paise + rupees for UI convenience
    items = []
    for r in rows:
        eq_paise = int(r["equity_paise"])
        items.append({
            "date": r["date"].isoformat(),
            "equity_paise": eq_paise,
            "equity_inr": eq_paise / 100.0,
        })

    return {"run_id": run_id, "items": items}


@router.get("/runs/{run_id}/fills")
def get_run_fills(run_id: str, db: Session = Depends(get_db)):
    ok = db.execute(text("SELECT 1 FROM runs WHERE id=:id"), {"id": run_id}).scalar()
    if not ok:
        raise HTTPException(status_code=404, detail="run not found")

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
            WHERE f.run_id = :id
            ORDER BY f.date ASC, f.order_id ASC
        """),
        {"id": run_id},
    ).mappings().all()

    items = []
    for r in rows:
        px = int(r["price_paise"])
        fee = int(r["fee_paise"])
        items.append({
            "date": r["date"].isoformat(),
            "ticker": r["ticker"],
            "side": r["side"],
            "qty": int(r["qty"]),
            "price_paise": px,
            "price_inr": px / 100.0,
            "fee_paise": fee,
            "fee_inr": fee / 100.0,
            "order_id": int(r["order_id"]),
        })

    return {"run_id": run_id, "items": items}


@router.get("/runs/{run_id}/metrics")
def get_run_metrics(run_id: str, db: Session = Depends(get_db)):
    ok = db.execute(text("SELECT 1 FROM runs WHERE id=:id"), {"id": run_id}).scalar()
    if not ok:
        raise HTTPException(status_code=404, detail="run not found")

    row = db.execute(
        text("""
            SELECT
              sharpe,
              max_drawdown_paise,
              win_rate,
              trades_closed,
              realized_pnl_paise,
              fees_paise
            FROM run_metrics
            WHERE run_id = :id
        """),
        {"id": run_id},
    ).mappings().first()

    if not row:
        # run may still be running; return empty instead of 404
        return {"run_id": run_id, "metrics": None}

    mdd = int(row["max_drawdown_paise"])
    rp = int(row["realized_pnl_paise"])
    fees = int(row["fees_paise"])

    return {
        "run_id": run_id,
        "metrics": {
            "sharpe": float(row["sharpe"]),
            "max_drawdown_paise": mdd,
            "max_drawdown_inr": mdd / 100.0,
            "win_rate": float(row["win_rate"]),
            "trades_closed": int(row["trades_closed"]),
            "realized_pnl_paise": rp,
            "realized_pnl_inr": rp / 100.0,
            "fees_paise": fees,
            "fees_inr": fees / 100.0,
        },
    }
