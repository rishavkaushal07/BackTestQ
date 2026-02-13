"""init

Revision ID: 0001_init
Revises:
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "symbols",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="INR"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "bars_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open_paise", sa.BigInteger(), nullable=False),
        sa.Column("high_paise", sa.BigInteger(), nullable=False),
        sa.Column("low_paise", sa.BigInteger(), nullable=False),
        sa.Column("close_paise", sa.BigInteger(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("symbol_id", "date", name="uq_bars_daily_symbol_date"),
    )
    op.create_index("ix_bars_daily_symbol_date", "bars_daily", ["symbol_id", "date"])
    op.create_index("ix_bars_daily_date", "bars_daily", ["date"])

    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("strategies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="QUEUED"),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_runs_status_created", "runs", ["status", "created_at"])

    op.create_table(
        "run_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="INFO"),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index("ix_run_logs_run_ts", "run_logs", ["run_id", "ts"])

    op.create_table(
        "run_equity",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("equity_paise", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("run_id", "date", name="uq_run_equity_run_date"),
    )
    op.create_index("ix_run_equity_run_date", "run_equity", ["run_id", "date"])

    op.create_table(
        "run_fills",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("qty", sa.BigInteger(), nullable=False),
        sa.Column("price_paise", sa.BigInteger(), nullable=False),
        sa.Column("fee_paise", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_run_fills_run_date", "run_fills", ["run_id", "date"])

    op.create_table(
        "run_metrics",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("sharpe", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_drawdown_paise", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trades_closed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("realized_pnl_paise", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("fees_paise", sa.BigInteger(), nullable=False, server_default="0"),
    )

def downgrade():
    op.drop_table("run_metrics")
    op.drop_index("ix_run_fills_run_date", table_name="run_fills")
    op.drop_table("run_fills")
    op.drop_index("ix_run_equity_run_date", table_name="run_equity")
    op.drop_table("run_equity")
    op.drop_index("ix_run_logs_run_ts", table_name="run_logs")
    op.drop_table("run_logs")
    op.drop_index("ix_runs_status_created", table_name="runs")
    op.drop_table("runs")
    op.drop_table("strategies")
    op.drop_index("ix_bars_daily_date", table_name="bars_daily")
    op.drop_index("ix_bars_daily_symbol_date", table_name="bars_daily")
    op.drop_table("bars_daily")
    op.drop_table("symbols")
