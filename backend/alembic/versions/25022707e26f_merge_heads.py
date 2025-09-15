"""merge heads

Revision ID: 25022707e26f
Revises: f1ca58b2f2ec, 4ef8f785ad19
Create Date: 2025-05-05 11:33:22.620539

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "25022707e26f"
down_revision = ("f1ca58b2f2ec", "4ef8f785ad19")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is a merge heads migration, no need to add columns again
    pass


def downgrade() -> None:
    pass
