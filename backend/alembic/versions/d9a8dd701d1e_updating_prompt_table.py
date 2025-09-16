"""add new table in prompt table
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d9a8dd701d1e"
down_revision = "c5eae4a75a1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompt",
        sa.Column("search_tool_description", sa.String(), nullable=True)
    )