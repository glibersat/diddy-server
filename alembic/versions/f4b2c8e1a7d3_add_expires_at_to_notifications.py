"""add expires_at to notifications

Revision ID: f4b2c8e1a7d3
Revises: 6801037652f3
Create Date: 2026-09-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4b2c8e1a7d3'
down_revision: Union[str, Sequence[str], None] = '6801037652f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing rows keep NULL, which the dispatcher treats as "never expires".
    op.add_column('notifications', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('notifications', 'expires_at')
