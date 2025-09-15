"""Add creator_assistant_id to chat_folder table

Revision ID: f8e9d7c6b5a4
Revises: a1b2c3d4e5f7
Create Date: 2024-12-19 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8e9d7c6b5a4'
down_revision = 'a1b2c3d4e5f7'
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    # Add creator_assistant_id column to chat_folder table
    op.add_column('chat_folder', sa.Column('creator_assistant_id', sa.Integer(), nullable=True))
    
    # Add foreign key constraint
    op.create_foreign_key(
        'chat_folder_creator_assistant_fk',
        'chat_folder',
        'persona',
        ['creator_assistant_id'],
        ['id']
    )


def downgrade() -> None:
    # Remove foreign key constraint
    op.drop_constraint('chat_folder_creator_assistant_fk', 'chat_folder', type_='foreignkey')
    
    # Remove creator_assistant_id column
    op.drop_column('chat_folder', 'creator_assistant_id')
