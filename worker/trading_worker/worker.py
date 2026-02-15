"""
worker.py — consolidated DB-backed worker that executes REAL backtests via Rust engine + Python strategy.

Assumptions about your DB schema (based on earlier migrations):
- runs(id, strategy_id, status, config_json, created_at, started_at, finished_at, error)
- strategies(id, code, name, created_at, updated_at)
- run_equity(run_id, date, equity_paise)
- run_fills(run_id, date, symbol_id, side, qty, price_paise, fee_paise, order_id)
- run_metrics(run_id, sharpe, max_drawdown_paise, win_rate, trades_closed, realized_pnl_paise, fees_paise)
- run_logs(run_id, ts, level, message)
- symbols(id, ticker, venue, asset_class, currency, created_at, updated_at)
- bars_daily(symbol_id, date, open_paise, high_paise, low_paise, close_paise, volume)

Engine contract (Rust PyO3 module):
- import trading_engine
- Engine(starting_cash_paise: int, fee_bps: int, slippage_bps: int)
- eng.on_bar(date:str, symbol:str, open:int, high:int, low:int, close:int, volume:int)
- eng.process_fills_for_date(date:str)
- eng.place_market_order(symbol:str, side:str, qty:int) -> order_id:int
- eng.end_of_day(date:str)
- eng.equity_curve() -> list[(date:str, equity_paise:int)]
- eng.fills() -> list[(date:str, symbol:str, side:str, qty:int, price:int, fee:int, order_id:int)]
- eng.metrics() -> object with attributes sharpe, max_drawdown_paise, win_rate, trades_closed, realized_pnl_paise, fees_paise

IMPORTANT:
- You currently have Python 3.14 venvs; PyO3 does not support 3.14 yet.
  This worker will import trading_engine only if it's installed. If not, it will
  fail the run with a clear error message.
"""

import time
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal


# ------------------------
# Logging helpers
# ------------------------

def log(db: Session, run_id: str, level: str, message: str) -> None:
    db.execute(
        text(
            """
            INSERT INTO run_logs (run_id, ts, level, message)
            VALUES (:run_id, now(), :level, :message)
            """
        ),
        {"run_id": run_id, "level": level, "message": message},
    )


# ------------------------
# Run lifecycle
# ------------------------

def claim_next_run(db: Session) -> Optional[str]:
    row = db.execute(
        text(
            """
            SELECT id
            FROM runs
            WHERE status = 'QUEUED'
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )
    ).fetchone()
    if not row:
        return None
    return str(row[0])


def mark_running(db: Session, run_id: str) -> None:
    db.execute(
        text(
            """
            UPDATE runs
            SET status = 'RUNNING',
                started_at = now(),
                error = NULL
            WHERE id = :id
            """
        ),
        {"id": run_id},
    )


def mark_completed(db: Session, run_id: str) -> None:
    db.execute(
        text(
            """
            UPDATE runs
            SET status = 'COMPLETED',
                finished_at = now()
            WHERE id = :id
            """
        ),
        {"id": run_id},
    )


def mark_failed(db: Session, run_id: str, err: str) -> None:
    db.execute(
        text(
            """
            UPDATE runs
            SET status = 'FAILED',
                finished_at = now(),
                error = :err
            WHERE id = :id
            """
        ),
        {"id": run_id, "err": err[:10000]},
    )


def get_run_config_and_strategy(db: Session, run_id: str) -> Tuple[dict, str, str]:
    """
    Returns: (config_json, strategy_code, strategy_id)
    """
    row = db.execute(
        text(
            """
            SELECT r.config_json, s.code, r.strategy_id
            FROM runs r
            LEFT JOIN strategies s ON s.id = r.strategy_id
            WHERE r.id = :id
            """
        ),
        {"id": run_id},
    ).fetchone()
    if not row:
        raise RuntimeError(f"run not found: {run_id}")
    cfg, code, sid = row
    # If the strategy is not persisted (no join result), allow inline code stored in run config under "strategy_code"
    if code is None:
        code = cfg.get("strategy_code")
    if not code:
        raise RuntimeError(f"strategy code not found for run: {run_id}")
    return cfg, code, str(sid) if sid is not None else ""


# ------------------------
# Market data loading
# ------------------------

@dataclass(frozen=True)
class Bar:
    d: str
    symbol: str
    open_paise: int
    high_paise: int
    low_paise: int
    close_paise: int
    volume: int


def load_bars_by_date(
    db: Session,
    tickers: List[str],
    start_date: str,
    end_date: str,
) -> Tuple[Dict[str, List[Bar]], Dict[str, str]]:
    """
    Loads daily bars for given tickers and date range.

    Returns:
      by_date: { "YYYY-MM-DD": [Bar(...), ...] } ordered by ticker
      symbol_id_by_ticker: { "RELIANCE": "<uuid>" }
    """
    rows = db.execute(
        text(
            """
            SELECT
              b.date,
              s.ticker,
              b.open_paise,
              b.high_paise,
              b.low_paise,
              b.close_paise,
              b.volume,
              s.id as symbol_id
            FROM bars_daily b
            JOIN symbols s ON s.id = b.symbol_id
            WHERE s.ticker = ANY(:tickers)
              AND b.date BETWEEN :start AND :end
            ORDER BY b.date ASC, s.ticker ASC
            """
        ),
        {"tickers": tickers, "start": start_date, "end": end_date},
    ).fetchall()

    by_date: Dict[str, List[Bar]] = {}
    symbol_id_by_ticker: Dict[str, str] = {}

    for r in rows:
        d, ticker, o, h, l, c, v, sym_id = r
        d_str = d.isoformat()
        symbol_id_by_ticker[str(ticker)] = str(sym_id)
        by_date.setdefault(d_str, []).append(
            Bar(
                d=d_str,
                symbol=str(ticker),
                open_paise=int(o),
                high_paise=int(h),
                low_paise=int(l),
                close_paise=int(c),
                volume=int(v or 0),
            )
        )

    return by_date, symbol_id_by_ticker


# ------------------------
# Strategy runtime (Python)
# ------------------------

class StrategyContext:
    """
    Minimal ctx passed into strategy code.
    Strategy author can call:
      ctx.buy(symbol, qty)
      ctx.sell(symbol, qty)
      ctx.cash()
      ctx.position(symbol)

    You can expand later:
      ctx.order_cancel(order_id)
      ctx.order_replace(...)
      ctx.log(...)
    """
    def __init__(self, engine: Any):
        self._engine = engine
        self._params: Dict[str, Any] = {}

    def set_param(self, k: str, v: Any) -> None:
        self._params[k] = v

    def param(self, k: str) -> Any:
        return self._params[k]

    def buy(self, symbol: str, qty: int) -> int:
        return int(self._engine.place_market_order(symbol, "BUY", int(qty)))

    def sell(self, symbol: str, qty: int) -> int:
        return int(self._engine.place_market_order(symbol, "SELL", int(qty)))

    def cash(self) -> int:
        return int(self._engine.cash())

    def position(self, symbol: str) -> int:
        return int(self._engine.position(symbol))


class BarObj:
    """
    What strategy sees: bar.open/bar.close etc. in integer paise.
    """
    def __init__(self, bar: Bar):
        self.date = bar.d
        self.symbol = bar.symbol
        self.open = bar.open_paise
        self.high = bar.high_paise
        self.low = bar.low_paise
        self.close = bar.close_paise
        self.volume = bar.volume


def compile_strategy(code: str):
    """
    Returns (init_fn, on_bar_fn)
    """
    g: Dict[str, Any] = {}
    exec(code, g, g)
    init_fn = g.get("init")
    on_bar_fn = g.get("on_bar")
    if on_bar_fn is None or not callable(on_bar_fn):
        raise RuntimeError("strategy must define on_bar(ctx, bar)")
    if init_fn is not None and not callable(init_fn):
        raise RuntimeError("init must be a function if defined")
    return init_fn, on_bar_fn


# ------------------------
# Backtest execution (Rust engine + Python strategy)
# ------------------------

def run_backtest(
    db: Session,
    run_id: str,
    cfg: dict,
    strategy_code: str,
) -> Tuple[List[Tuple[str, int]], List[Tuple[str, str, str, int, int, int, int]], Any, Dict[str, str]]:
    """
    Returns: (equity_curve, fills, metrics_obj, symbol_id_by_ticker)
    """
    try:
        import trading_engine  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Rust engine module 'trading_engine' not available. "
            "This usually means PyO3 build failed (Python 3.14 not supported). "
            "Recreate worker venv using Python 3.12 and run 'maturin develop' in python_api/engine. "
            f"Import error: {repr(e)}"
        ) from e

    # Resolve symbols
    if cfg.get("portfolio_id"):
        tickers = get_portfolio_symbols(db, cfg["portfolio_id"])
    else:
        tickers = list(cfg.get("symbols") or [])

    if not tickers:
        raise RuntimeError("run config has no symbols (portfolio empty or symbols missing)")

    log(db,run_id,"INFO",f"resolved symbols: {tickers} (mode={'PORTFOLIO' if cfg.get('portfolio_id') else 'SYMBOLS'})")

    start_date = str(cfg["start_date"])
    end_date = str(cfg["end_date"])

    by_date, symbol_id_by_ticker = load_bars_by_date(db, tickers, start_date, end_date)
    if not by_date:
        raise RuntimeError(
            f"No bars found for symbols={tickers} between {start_date} and {end_date}. "
            "Load daily bars into bars_daily first."
        )

    eng = trading_engine.Engine(
        int(cfg["starting_cash_paise"]),
        int(cfg.get("fee_bps", 1)),
        int(cfg.get("slippage_bps", 2)),
    )

    init_fn, on_bar_fn = compile_strategy(strategy_code)
    ctx = StrategyContext(eng)

    if init_fn is not None:
        init_fn(ctx)

    # Iterate dates in sorted order
    for d in sorted(by_date.keys()):
        bars = by_date[d]

        # Provide today's bars to engine
        for bar in bars:
            eng.on_bar(
                bar.d,
                bar.symbol,
                int(bar.open_paise),
                int(bar.high_paise),
                int(bar.low_paise),
                int(bar.close_paise),
                int(bar.volume),
            )

        # Fill orders scheduled for NEXT_OPEN at today's open
        eng.process_fills_for_date(d)

        # Run strategy per bar
        for bar in bars:
            on_bar_fn(ctx, BarObj(bar))

        # End-of-day accounting
        eng.end_of_day(d)

    equity_curve = [(str(d), int(eq)) for (d, eq) in eng.equity_curve()]
    fills = [(str(d), str(sym), str(side), int(qty), int(px), int(fee), int(oid)) for (d, sym, side, qty, px, fee, oid) in eng.fills()]
    metrics = eng.metrics()

    return equity_curve, fills, metrics, symbol_id_by_ticker


# ------------------------
# Persist results
# ------------------------

def clear_previous_results(db: Session, run_id: str) -> None:
    db.execute(text("DELETE FROM run_equity WHERE run_id = :id"), {"id": run_id})
    db.execute(text("DELETE FROM run_fills  WHERE run_id = :id"), {"id": run_id})
    db.execute(text("DELETE FROM run_metrics WHERE run_id = :id"), {"id": run_id})


def write_results(
    db: Session,
    run_id: str,
    equity_curve: List[Tuple[str, int]],
    fills: List[Tuple[str, str, str, int, int, int, int]],
    metrics: Any,
    symbol_id_by_ticker: Dict[str, str],
) -> None:
    clear_previous_results(db, run_id)

    # Equity
    for (d, eq) in equity_curve:
        db.execute(
            text(
                """
                INSERT INTO run_equity (run_id, date, equity_paise)
                VALUES (:run_id, :date, :eq)
                """
            ),
            {"run_id": run_id, "date": d, "eq": int(eq)},
        )

    # Fills
    for (d, sym, side, qty, px, fee, oid) in fills:
        sym_id = symbol_id_by_ticker.get(sym)
        if not sym_id:
            continue
        db.execute(
            text(
                """
                INSERT INTO run_fills (run_id, date, symbol_id, side, qty, price_paise, fee_paise, order_id)
                VALUES (:run_id, :date, :symbol_id, :side, :qty, :price, :fee, :oid)
                """
            ),
            {
                "run_id": run_id,
                "date": d,
                "symbol_id": sym_id,
                "side": side,
                "qty": int(qty),
                "price": int(px),
                "fee": int(fee),
                "oid": int(oid),
            },
        )

    # Metrics (Sharpe may be 0.0 for now; we’ll compute properly next)
    # Compute sharpe from equity curve as a fallback if engine didn't provide one.
    def compute_sharpe_from_equity(e_curve: List[Tuple[str, int]]) -> float:
        # Convert equity paise values to floats and compute simple daily returns.
        if not e_curve or len(e_curve) < 2:
            return 0.0
        vals = [float(v) for (_d, v) in e_curve]
        rets: List[float] = []
        for i in range(1, len(vals)):
            prev = vals[i - 1]
            if prev == 0:
                continue
            rets.append((vals[i] / prev) - 1.0)
        if not rets:
            return 0.0
        mean = sum(rets) / len(rets)
        # sample standard deviation
        if len(rets) > 1:
            variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            sd = math.sqrt(variance)
        else:
            sd = 0.0
        if sd == 0.0:
            return 0.0
        # annualize assuming ~252 trading days
        sharpe = (mean / sd) * (252 ** 0.5)
        return float(sharpe)

    computed_sharpe = compute_sharpe_from_equity(equity_curve)
    engine_sharpe = None
    try:
        engine_sharpe = getattr(metrics, "sharpe", None)
        if engine_sharpe is not None:
            engine_sharpe = float(engine_sharpe)
    except Exception:
        engine_sharpe = None

    sharpe_to_store = engine_sharpe if (engine_sharpe is not None and engine_sharpe != 0.0) else computed_sharpe
    # Compute max drawdown pct fallback from equity curve if engine didn't provide it.
    def compute_max_drawdown_pct(e_curve: List[Tuple[str, int]]) -> float:
        if not e_curve:
            return 0.0
        vals = [float(v) for (_d, v) in e_curve]
        peak = vals[0]
        max_dd_pct = 0.0
        for v in vals:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            if dd > max_dd_pct:
                max_dd_pct = dd
        return max_dd_pct * 100.0

    computed_max_dd_pct = compute_max_drawdown_pct(equity_curve)
    engine_max_dd_pct = None
    try:
        engine_max_dd_pct = getattr(metrics, "max_drawdown_pct", None)
        if engine_max_dd_pct is not None:
            engine_max_dd_pct = float(engine_max_dd_pct)
    except Exception:
        engine_max_dd_pct = None

    max_drawdown_pct_to_store = engine_max_dd_pct if (engine_max_dd_pct is not None and engine_max_dd_pct != 0.0) else computed_max_dd_pct

    db.execute(
        text(
            """
            INSERT INTO run_metrics (run_id, sharpe, max_drawdown_paise, max_drawdown_pct, win_rate, trades_closed, realized_pnl_paise, fees_paise, annual_return_pct, volatility)
            VALUES (:run_id, :sharpe, :mdd, :mdd_pct, :wr, :tc, :rp, :fees, :annual_return_pct, :volatility)
            """
        ),
        {
            "run_id": run_id,
            "sharpe": float(sharpe_to_store),
            "mdd": int(getattr(metrics, "max_drawdown_paise", 0)),
            "mdd_pct": float(max_drawdown_pct_to_store),
            "wr": float(getattr(metrics, "win_rate", 0.0)),
            "tc": int(getattr(metrics, "trades_closed", 0)),
            "rp": int(getattr(metrics, "realized_pnl_paise", 0)),
            "fees": int(getattr(metrics, "fees_paise", 0)),
            "annual_return_pct": float(getattr(metrics, "annual_return_pct", 0.0)),
            "volatility": float(getattr(metrics, "volatility", 0.0)),
        },
    )

def get_portfolio_symbols(db: Session, portfolio_id: str) -> list[str]:
    rows = db.execute(text("""
        SELECT s.ticker
        FROM portfolio_symbols ps
        JOIN symbols s ON s.id = ps.symbol_id
        WHERE ps.portfolio_id = :pid
    """), {"pid": portfolio_id}).fetchall()

    if not rows:
        raise RuntimeError("Portfolio has no symbols")

    return [r[0] for r in rows]


# ------------------------
# Main worker loop
# ------------------------

def run_once() -> bool:
    db = SessionLocal()
    run_id: Optional[str] = None
    try:
        # Transaction 1: claim + mark running + read config/strategy
        db.begin()
        run_id = claim_next_run(db)
        if not run_id:
            db.rollback()
            return False

        mark_running(db, run_id)
        cfg, strat_code, strat_id = get_run_config_and_strategy(db, run_id)
        log(db, run_id, "INFO", f"{settings.WORKER_NAME} claimed run {run_id}")
        log(db, run_id, "INFO", f"strategy_id={strat_id}")
        log(db, run_id, "INFO", f"config: {cfg}")
        db.commit()

        # Transaction 2: execute backtest and write results
        db.begin()
        log(db, run_id, "INFO", "starting backtest execution (rust engine + python strategy)")

        equity_curve, fills, metrics, symbol_id_by_ticker = run_backtest(db, run_id, cfg, strat_code)

        log(db, run_id, "INFO", f"equity points={len(equity_curve)} fills={len(fills)}")
        write_results(db, run_id, equity_curve, fills, metrics, symbol_id_by_ticker)

        mark_completed(db, run_id)
        log(db, run_id, "INFO", "run completed")
        db.commit()
        return True

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass

        # Best-effort mark failed
        try:
            if run_id:
                db.begin()
                mark_failed(db, run_id, repr(e))
                log(db, run_id, "ERROR", f"run failed: {repr(e)}")
                db.commit()
        except Exception:
            pass

        return False

    finally:
        db.close()


def main() -> None:
    print(f"[worker] starting {settings.WORKER_NAME} poll={settings.POLL_INTERVAL_SECS}s db={settings.DATABASE_URL}")
    while True:
        did = run_once()
        if not did:
            time.sleep(settings.POLL_INTERVAL_SECS)


if __name__ == "__main__":
    main()
