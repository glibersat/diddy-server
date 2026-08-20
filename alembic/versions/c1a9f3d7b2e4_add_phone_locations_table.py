"""add phone_locations table

Revision ID: c1a9f3d7b2e4
Revises: d31215271aaa
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a9f3d7b2e4'
down_revision: Union[str, Sequence[str], None] = 'd31215271aaa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('phone_locations',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('accuracy_m', sa.Float(), nullable=True),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_phone_locations_recorded_at'), 'phone_locations', ['recorded_at'], unique=False)
    op.create_index(op.f('ix_phone_locations_user_id'), 'phone_locations', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_phone_locations_user_id'), table_name='phone_locations')
    op.drop_index(op.f('ix_phone_locations_recorded_at'), table_name='phone_locations')
    op.drop_table('phone_locations')
