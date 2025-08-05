"""create tables

Revision ID: e7f487d126e9
Revises: 
Create Date: 2025-08-05 03:33:49.922192

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from apy.database import Base


# revision identifiers, used by Alembic.
revision: str = 'e7f487d126e9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by creating all tables."""
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    """Downgrade schema by dropping all tables."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
