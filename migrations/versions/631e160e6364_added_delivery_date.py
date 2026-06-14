"""added delivery date

Revision ID: 631e160e6364
Revises: f5ae5439d4b6
Create Date: 2026-06-14 19:47:07.625410

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '631e160e6364'
down_revision = 'f5ae5439d4b6'
branch_labels = None
depends_on = None


def upgrade():
  

    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('delivery_date', sa.Date(), nullable=True))
        