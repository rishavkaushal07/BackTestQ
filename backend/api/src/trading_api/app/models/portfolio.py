import uuid
from datetime import datetime
from sqlalchemy import Column, Text, TIMESTAMP, Float, ForeignKey, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    symbols = relationship("PortfolioSymbol", cascade="all, delete-orphan")

class PortfolioSymbol(Base):
    __tablename__ = "portfolio_symbols"

    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True)
    symbol_id = Column(ForeignKey("symbols.id"), primary_key=True)
    weight = Column(Float, nullable=True)
