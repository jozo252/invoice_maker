"""Add approved job extras without changing accepted offer revisions.

Revision ID: c42f980d7b25
Revises: f36b7c0912da
"""

from alembic import op
import sqlalchemy as sa


revision = "c42f980d7b25"
down_revision = "f36b7c0912da"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approval_note", sa.String(500), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_job_change_quantity_positive"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_job_change_price_nonnegative"),
        sa.CheckConstraint("total_cents >= 0", name="ck_job_change_total_nonnegative"),
    )
    op.create_index("ix_job_changes_user_job", "job_changes", ["user_id", "job_id"])


def downgrade():
    # Disposable databases only; production downgrade would lose agreements.
    op.drop_index("ix_job_changes_user_job", table_name="job_changes")
    op.drop_table("job_changes")
