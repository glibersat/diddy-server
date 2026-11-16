"""add phone_seen_at and watch_seen_at to users

Revision ID: a7c3e9d2f1b5
Revises: b7e2d94c1f60
Create Date: 2026-11-16 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e9d2f1b5'
down_revision: Union[str, Sequence[str], None] = 'b7e2d94c1f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NULL until the phone next connects.
    op.add_column('users', sa.Column('phone_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('watch_seen_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'watch_seen_at')
    op.drop_column('users', 'phone_seen_at')
