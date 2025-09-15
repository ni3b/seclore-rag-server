"""merge heads

Revision ID: 4ef8f785ad19
Revises: 21b3de4d9539
Create Date: 2025-05-05 10:10:16.596757

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4ef8f785ad19"
down_revision = "d9a8dd701d1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is a merge heads migration, no need to add columns again
    pass


def downgrade() -> None:
    pass
