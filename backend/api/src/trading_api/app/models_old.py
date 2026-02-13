import uuid
from datetime import datetime
from sqlalchemy import (
    String, Text, DateTime, Boolean, ForeignKey, BigInteger,
    JSON, Date, Integer, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from sqlalchemy import Float

class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # NSE ticker, e.g. RELIANCE
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

class BarDaily(Base):
    __tablename__ = "bars_daily"
    __table_args__ = (
        UniqueConstraint("symbol_id", "date", name="uq_bars_daily_symbol_date"),
        Index("ix_bars_daily_symbol_date", "symbol_id", "date"),
        Index("ix_bars_daily_date", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)

    open_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    high_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    low_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    close_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("strategies.id", ondelete="RESTRICT"), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    strategy = relationship("Strategy")

class RunLog(Base):
    __tablename__ = "run_logs"
    __table_args__ = (
        Index("ix_run_logs_run_ts", "run_id", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)

class RunEquity(Base):
    __tablename__ = "run_equity"
    __table_args__ = (
        UniqueConstraint("run_id", "date", name="uq_run_equity_run_date"),
        Index("ix_run_equity_run_date", "run_id", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    equity_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

class RunFill(Base):
    __tablename__ = "run_fills"
    __table_args__ = (
        Index("ix_run_fills_run_date", "run_id", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)

    symbol_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # BUY/SELL
    qty: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

class RunMetrics(Base):
    __tablename__ = "run_metrics"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    sharpe: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_drawdown_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    trades_closed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    realized_pnl_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    fees_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
