"""Add local CRM receipt drafts and optional job planning details.

Revision ID: d72c913f1b08
Revises: 631e160e6364
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa


revision = "d72c913f1b08"
down_revision = "631e160e6364"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_plans",
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("agreed_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "agreed_price_cents IS NULL OR agreed_price_cents >= 0",
            name="ck_job_plans_agreed_price_nonnegative",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_table(
        "job_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_name", sa.String(length=100), nullable=False),
        sa.Column("original_name", sa.String(length=200), nullable=False),
        sa.Column("mime", sa.String(length=30), nullable=False),
        sa.Column("vendor", sa.String(length=120), server_default="", nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("ocr_text", sa.Text(), server_default="", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'confirmed')", name="ck_job_receipts_status"),
        sa.CheckConstraint(
            "amount_cents IS NULL OR (amount_cents >= 0 AND amount_cents <= 1000000000)",
            name="ck_job_receipts_amount_range",
        ),
        sa.CheckConstraint(
            "status != 'confirmed' OR (amount_cents IS NOT NULL AND amount_cents > 0 "
            "AND receipt_date IS NOT NULL AND length(trim(vendor)) > 0 "
            "AND confirmed_at IS NOT NULL)",
            name="ck_job_receipts_confirmed_complete",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_job_receipts_revision_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sha256", name="uq_job_receipts_user_sha256"),
    )
    op.create_index("ix_job_receipts_user_job", "job_receipts", ["user_id", "job_id"])


def downgrade():
    # File objects are deliberately outside the database lifecycle. Downgrading
    # this schema never removes any uploaded originals from private storage.
    op.drop_index("ix_job_receipts_user_job", table_name="job_receipts")
    op.drop_table("job_receipts")
    op.drop_table("job_plans")
