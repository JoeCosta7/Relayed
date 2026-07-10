"""add previous api key columns to customer

Revision ID: 4843809c7f81
Revises: 1317b3d76946
Create Date: 2026-07-10 15:23:02.396888

"""
from typing import Sequence, Union
import sqlmodel
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4843809c7f81'
down_revision: Union[str, Sequence[str], None] = '1317b3d76946'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('customer', sa.Column('previous_api_key_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('customer', sa.Column('previous_api_key_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_customer_previous_api_key_hash'), 'customer', ['previous_api_key_hash'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_customer_previous_api_key_hash'), table_name='customer')
    op.drop_column('customer', 'previous_api_key_expires_at')
    op.drop_column('customer', 'previous_api_key_hash')
