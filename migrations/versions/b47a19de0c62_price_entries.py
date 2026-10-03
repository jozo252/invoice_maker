"""Add owner's small labor/material price list.

Revision ID: b47a19de0c62
Revises: c42f980d7b25
"""

from alembic import op
import sqlalchemy as sa


revision = "b47a19de0c62"
down_revision = "c42f980d7b25"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "price_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("sale_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("cost_cents", sa.BigInteger(), nullable=True),
        sa.Column("source_note", sa.String(200), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("sale_price_cents >= 0", name="ck_price_entry_sale_nonnegative"),
        sa.CheckConstraint("cost_cents IS NULL OR cost_cents >= 0", name="ck_price_entry_cost_nonnegative"),
    )
    op.create_index("ix_price_entries_user_kind", "price_entries", ["user_id", "kind"])


def downgrade():
    # Disposable databases only; production downgrade would discard prices.
    op.drop_index("ix_price_entries_user_kind", table_name="price_entries")
    op.drop_table("price_entries")
