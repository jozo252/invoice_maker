"""Add work sites, explicit case links and immutable offer revisions.

Revision ID: ea42d6a90b17
Revises: d72c913f1b08

The upgrade only adds nullable columns and new tables. Existing offers remain
unlinked until a person reconciles their client and acceptance evidence.
"""

from alembic import op
import sqlalchemy as sa


revision = "ea42d6a90b17"
down_revision = "d72c913f1b08"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("label", sa.String(120), nullable=True),
        sa.Column("street", sa.String(200), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(50), nullable=True),
        sa.Column("access_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sites_user_id", "sites", ["user_id"])

    for column in (
        sa.Column("customer_phone", sa.String(32), nullable=True),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("work_type", sa.String(50), nullable=True),
        sa.Column("next_action", sa.String(255), nullable=True),
        sa.Column("next_action_due", sa.Date(), nullable=True),
    ):
        op.add_column("lead", column)

    op.add_column("offer", sa.Column("client_id", sa.Integer(), nullable=True))
    op.add_column("offer", sa.Column("site_id", sa.Integer(), nullable=True))

    op.create_table(
        "offer_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offer.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("delivery_note", sa.String(500), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("acceptance_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("offer_id", "version", name="uq_offer_revision_version"),
    )
    op.create_index("ix_offer_revisions_user_offer", "offer_revisions", ["user_id", "offer_id"])

    op.create_table(
        "work_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("lead.id"), nullable=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("(lead_id IS NOT NULL) != (job_id IS NOT NULL)", name="ck_work_activity_one_case"),
    )
    op.create_index("ix_work_activities_user_starts", "work_activities", ["user_id", "starts_at"])

    op.add_column("jobs", sa.Column("lead_id", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("site_id", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("offer_revision_id", sa.Integer(), nullable=True))
    op.create_index("uq_jobs_offer_revision_id", "jobs", ["offer_revision_id"], unique=True)

    op.add_column("invoices", sa.Column("job_id", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("offer_revision_id", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("buyer_snapshot", sa.JSON(), nullable=True))
    op.add_column("invoices", sa.Column("seller_snapshot", sa.JSON(), nullable=True))
    for column in (
        sa.Column("room_label", sa.String(100), nullable=True),
        sa.Column("element_label", sa.String(100), nullable=True),
        sa.Column("cable_type", sa.String(100), nullable=True),
        sa.Column("route_note", sa.String(500), nullable=True),
    ):
        op.add_column("job_attachments", column)


def downgrade():
    # Use only on a disposable database. Production rollback should restore a
    # consistent database-plus-attachments backup, never discard live links.
    op.drop_column("invoices", "seller_snapshot")
    op.drop_column("invoices", "buyer_snapshot")
    for name in ("route_note", "cable_type", "element_label", "room_label"):
        op.drop_column("job_attachments", name)
    op.drop_column("invoices", "offer_revision_id")
    op.drop_column("invoices", "job_id")
    op.drop_index("ix_work_activities_user_starts", table_name="work_activities")
    op.drop_table("work_activities")
    op.drop_index("uq_jobs_offer_revision_id", table_name="jobs")
    op.drop_column("jobs", "offer_revision_id")
    op.drop_column("jobs", "site_id")
    op.drop_column("jobs", "lead_id")
    op.drop_index("ix_offer_revisions_user_offer", table_name="offer_revisions")
    op.drop_table("offer_revisions")
    op.drop_column("offer", "site_id")
    op.drop_column("offer", "client_id")
    for name in ("next_action_due", "next_action", "work_type", "source", "site_id", "client_id", "customer_phone"):
        op.drop_column("lead", name)
    op.drop_index("ix_sites_user_id", table_name="sites")
    op.drop_table("sites")
