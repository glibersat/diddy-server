"""add labels to notifications

Revision ID: c4d8a1f2e9b7
Revises: a7c3e9d2f1b5
Create Date: 2026-11-21 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8a1f2e9b7'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9d2f1b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NULL keeps the watch's own DONE and "N min" buttons.
    op.add_column('notifications', sa.Column('labels', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('notifications', 'labels')
