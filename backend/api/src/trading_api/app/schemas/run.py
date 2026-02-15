from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator
from uuid import UUID

# ---- Runs ----
class RunCreate(BaseModel):
    # Either reference an existing strategy by id OR provide inline strategy code.
    strategy_id: UUID | None = None
    strategy_code: str | None = None

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
    def validate_inputs(self):
        if not self.symbols and not self.portfolio_id:
            raise ValueError("Provide either symbols or portfolio_id")
        if self.symbols and self.portfolio_id:
            raise ValueError("Provide only one of symbols or portfolio_id")
        if not self.strategy_id and not self.strategy_code:
            raise ValueError("Provide either strategy_id or inline strategy_code")
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
    class Config:
        from_attributes = True


class RunsListOut(BaseModel):
    items: list[RunOut]
    total: int
    page: int
    page_size: int