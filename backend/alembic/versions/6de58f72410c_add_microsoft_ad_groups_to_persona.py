"""add_microsoft_ad_groups_to_persona

Revision ID: 6de58f72410c
Revises: a1b2c3d4e5f6
Create Date: 2025-07-21 03:02:57.165548

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import Text


# revision identifiers, used by Alembic.
revision = '6de58f72410c'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add microsoft_ad_groups column to persona table
    op.add_column('persona', sa.Column('microsoft_ad_groups', postgresql.ARRAY(sa.Text()), nullable=True, server_default='{}'))


def downgrade() -> None:
    # Remove microsoft_ad_groups column from persona table
    op.drop_column('persona', 'microsoft_ad_groups') 
