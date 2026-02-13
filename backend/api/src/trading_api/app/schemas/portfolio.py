from pydantic import BaseModel
from uuid import UUID

class PortfolioCreate(BaseModel):
    name: str
    tickers: list[str]

class PortfolioOut(BaseModel):
    id: UUID
    name: str
    tickers: list[str]
