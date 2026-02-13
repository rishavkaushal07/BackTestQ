from sqlalchemy import Column, Text, TIMESTAMP, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base

class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True))
    updated_at = Column(TIMESTAMP(timezone=True))

    symbols = relationship("PortfolioSymbol", cascade="all, delete-orphan")

class PortfolioSymbol(Base):
    __tablename__ = "portfolio_symbols"

    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True)
    symbol_id = Column(ForeignKey("symbols.id"), primary_key=True)
    weight = Column(Float, nullable=True)
