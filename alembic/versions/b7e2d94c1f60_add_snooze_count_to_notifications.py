"""add snooze_count to notifications

Revision ID: b7e2d94c1f60
Revises: f4b2c8e1a7d3

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2d94c1f60'
down_revision: Union[str, Sequence[str], None] = 'f4b2c8e1a7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'notifications',
        sa.Column('snooze_count', sa.Integer(), nullable=False, server_default='0'),
    )
    # Rows acked before this column existed were snoozed at least once.
    op.execute("UPDATE notifications SET snooze_count = 1 WHERE ack_action = 'snoozed'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('notifications', 'snooze_count')
