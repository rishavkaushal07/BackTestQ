from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from uuid import UUID

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