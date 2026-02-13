from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from uuid import UUID

class RunEquityPoint(BaseModel):
    date: date
    equity_paise: int
    equity_inr: float


class RunFillOut(BaseModel):
    date: date
    ticker: str
    side: str
    qty: int
    price_paise: int
    price_inr: float
    fee_paise: int
    fee_inr: float
    order_id: int


class RunMetricsOut(BaseModel):
    run_id: UUID
    sharpe: float
    max_drawdown_paise: int
    max_drawdown_inr: float
    win_rate: float
    trades_closed: int
    realized_pnl_paise: int
    realized_pnl_inr: float
    fees_paise: int
    fees_inr: float
