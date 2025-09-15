"""add user default assistant id

Revision ID: a1b2c3d4e5f6
Revises: 4b5b8044d384
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "4b5b8044d384"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add default_assistant_id column to user table
    op.add_column("user", sa.Column("default_assistant_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove default_assistant_id column from user table
    op.drop_column("user", "default_assistant_id") 