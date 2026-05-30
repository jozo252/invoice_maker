"""jobs

Revision ID: f243990c27b7
Revises: 454545_make_clients_nullable
Create Date: 2026-05-29 18:57:20.150891

"""
from alembic import op
import sqlalchemy as sa


revision = 'f243990c27b7'
down_revision = '454545_make_clients_nullable'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('offer', schema=None) as batch_op:
        batch_op.add_column(sa.Column('job_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_offer_job_id_jobs',
            'jobs',
            ['job_id'],
            ['id']
        )


def downgrade():
    with op.batch_alter_table('offer', schema=None) as batch_op:
        batch_op.drop_constraint('fk_offer_job_id_jobs', type_='foreignkey')
        batch_op.drop_column('job_id')