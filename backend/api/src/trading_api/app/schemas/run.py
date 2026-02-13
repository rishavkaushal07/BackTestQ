from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator
from uuid import UUID

# ---- Runs ----
class RunCreate(BaseModel):
    strategy_id: UUID

    # old way
    symbols: Optional[list[str]] = None

    # new way
    portfolio_id: Optional[UUID] = None

    start_date: date
    end_date: date

    starting_cash_paise: Optional[int] = None
    fee_bps: Optional[int] = None
    slippage_bps: Optional[int] = None

    @model_validator(mode="after")
    def validate_symbols_or_portfolio(self):
        if not self.symbols and not self.portfolio_id:
            raise ValueError("Provide either symbols or portfolio_id")
        if self.symbols and self.portfolio_id:
            raise ValueError("Provide only one of symbols or portfolio_id")
        return self

class RunOut(BaseModel):
    id: UUID
    strategy_id: UUID
    status: str
    config_json: dict[str, Any]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]