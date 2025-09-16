"""add assistant_id to inputprompt table

Revision ID: 03ad742ec159
Revises: 8e050b834d25
Create Date: 2025-06-30 11:37:09.774799

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '03ad742ec159'
down_revision = '8e050b834d25'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add assistant_id column to inputprompt table
    op.add_column('inputprompt', sa.Column('assistant_id', sa.Integer(), nullable=True))
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_inputprompt_assistant_id_persona',
        'inputprompt', 'persona',
        ['assistant_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Remove foreign key constraint if it exists
    try:
        op.drop_constraint('fk_inputprompt_assistant_id_persona', 'inputprompt', type_='foreignkey')
    except Exception:
        # Constraint doesn't exist, skip
        pass
    
    # Remove assistant_id column if it exists
    try:
        op.drop_column('inputprompt', 'assistant_id')
    except Exception:
        # Column doesn't exist, skip
        pass
