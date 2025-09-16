"""fix_inputprompt_user_foreign_key_constraint

Revision ID: db11d925ffe5
Revises: 03ad742ec159
Create Date: 2025-06-30 13:29:20.680168

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'db11d925ffe5'
down_revision = '03ad742ec159'
branch_labels = None
depends_on = None


def upgrade() -> None:
    try:
        # Drop the incorrect foreign key constraint for user_id (which incorrectly references inputprompt.id)
        op.drop_constraint('inputprompt__user_user_id_fkey', 'inputprompt__user', type_='foreignkey')
    except Exception:
        # Constraint doesn't exist, skip
        pass
    
    # Add the correct foreign key constraint for user_id (should reference user.id)
    op.create_foreign_key('inputprompt__user_user_id_fkey', 'inputprompt__user', 'user', ['user_id'], ['id'])


def downgrade() -> None:
    # Drop the correct foreign key constraint if it exists
    try:
        op.drop_constraint('inputprompt__user_user_id_fkey', 'inputprompt__user', type_='foreignkey')
    except Exception:
        # Constraint doesn't exist, skip
        pass
    
    # Add back the incorrect foreign key constraint (for rollback) - only if it doesn't exist
    try:
        op.create_foreign_key('inputprompt__user_user_id_fkey', 'inputprompt__user', 'inputprompt', ['user_id'], ['id'])
    except Exception:
        # Constraint creation failed, skip
        pass
