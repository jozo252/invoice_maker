
from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.alter_column('ico', existing_type=sa.String(length=20), nullable=True)
        batch_op.alter_column('dic', existing_type=sa.String(length=20), nullable=True)
        batch_op.alter_column('street', existing_type=sa.String(length=100), nullable=True)
        batch_op.alter_column('city', existing_type=sa.String(length=50), nullable=True)
        batch_op.alter_column('zip_code', existing_type=sa.String(length=20), nullable=True)
        batch_op.alter_column('country', existing_type=sa.String(length=50), nullable=True)
        batch_op.alter_column('email', existing_type=sa.String(length=100), nullable=True)
        batch_op.alter_column('phone', existing_type=sa.String(length=20), nullable=True)
        batch_op.alter_column('iban', existing_type=sa.String(length=34), nullable=True)
        batch_op.alter_column('bic', existing_type=sa.String(length=11), nullable=True)
        batch_op.alter_column('ic_dph', existing_type=sa.String(length=20), nullable=True)

def downgrade():
    pass