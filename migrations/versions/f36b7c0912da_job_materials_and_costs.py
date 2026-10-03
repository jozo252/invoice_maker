"""Add small job material checklist and confirmed direct costs.

Revision ID: f36b7c0912da
Revises: ea42d6a90b17
"""

from alembic import op
import sqlalchemy as sa


revision = "f36b7c0912da"
down_revision = "ea42d6a90b17"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_job_material_quantity_positive"),
    )
    op.create_index("ix_job_materials_user_job", "job_materials", ["user_id", "job_id"])
    op.create_table(
        "job_costs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column("hourly_cost_cents", sa.BigInteger(), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount_cents >= 0", name="ck_job_cost_nonnegative"),
        sa.CheckConstraint("minutes IS NULL OR minutes > 0", name="ck_job_cost_minutes_positive"),
    )
    op.create_index("ix_job_costs_user_job", "job_costs", ["user_id", "job_id"])


def downgrade():
    # Disposable databases only; never discard live cost data.
    op.drop_index("ix_job_costs_user_job", table_name="job_costs")
    op.drop_table("job_costs")
    op.drop_index("ix_job_materials_user_job", table_name="job_materials")
    op.drop_table("job_materials")
