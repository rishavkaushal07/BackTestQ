from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_portfolios"
down_revision = "0001_init"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "portfolios",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "portfolio_symbols",
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "symbol_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("symbols.id"),
            primary_key=True,
        ),
        sa.Column("weight", sa.Float(), nullable=True),
    )

    op.create_index(
        "ix_portfolio_symbols_portfolio",
        "portfolio_symbols",
        ["portfolio_id"],
    )

def downgrade():
    op.drop_index("ix_portfolio_symbols_portfolio")
    op.drop_table("portfolio_symbols")
    op.drop_table("portfolios")
