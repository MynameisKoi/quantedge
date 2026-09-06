"""initial placeholder

Revision ID: 0001
Revises:
Create Date: 2026-03-22

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Schema models land in a follow-up migration once trade journal ORM is finalized.
    pass


def downgrade() -> None:
    pass
