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