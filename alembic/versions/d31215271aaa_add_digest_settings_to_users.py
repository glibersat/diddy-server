"""add digest settings to users

Revision ID: d31215271aaa
Revises: a425cf2a8e3b
Create Date: 2026-08-18 20:44:35.418543

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd31215271aaa'
down_revision: Union[str, Sequence[str], None] = 'a425cf2a8e3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users", sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("users", sa.Column("digest_time", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "digest_time")
    op.drop_column("users", "digest_enabled")
