from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from uuid import UUID

# ---- Strategies ----
class StrategyCreate(BaseModel):
    name: str
    code: str

class StrategyOut(BaseModel):
    id: UUID
    name: str
    code: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None

# ---- Runs ----
class RunCreate(BaseModel):
    strategy_id: UUID
    symbols: list[str] = Field(..., min_length=1)  # NSE tickers
    start_date: date
    end_date: date

    starting_cash_paise: Optional[int] = None
    fee_bps: Optional[int] = None
    slippage_bps: Optional[int] = None

class RunOut(BaseModel):
    id: UUID
    strategy_id: UUID
    status: str
    config_json: dict[str, Any]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]

class Config:
        from_attributes = True

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


class SymbolOut(BaseModel):
    id: UUID
    ticker: str
    name: str | None = None
    currency: str
    is_active: bool

    class Config:
        from_attributes = True


class BarOut(BaseModel):
    date: date
    open_paise: int
    high_paise: int
    low_paise: int
    close_paise: int
    volume: int
    open_inr: float
    high_inr: float
    low_inr: float
    close_inr: float
