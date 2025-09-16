"""Remove inputprompt unique constraint

Revision ID: 4b5b8044d384
Revises: db11d925ffe5
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4b5b8044d384'
down_revision = 'db11d925ffe5'
branch_labels = None
depends_on = None


def upgrade():
    # Remove the unique constraint that's causing the index size issue
    # This constraint combines prompt, content, assistant_id, and user_id
    # The content field is too large for the index
    
    try:
        # Drop the unique constraint
        op.drop_constraint('uq_inputprompt_prompt_content_assistant_user', 'inputprompt', type_='unique')
        print("Successfully dropped unique constraint: uq_inputprompt_prompt_content_assistant_user")
    except Exception as e:
        print(f"Unique constraint uq_inputprompt_prompt_content_assistant_user not found or already dropped: {e}")
        # Don't fail the migration if constraint doesn't exist
        pass
    
    try:
        # Also try to drop any related indexes that might exist
        index_names = [
            'ix_inputprompt_prompt_content_assistant_user',
            'idx_inputprompt_prompt_content_assistant_user',
            'inputprompt_prompt_content_assistant_user_idx'
        ]
        
        for index_name in index_names:
            try:
                op.drop_index(index_name, table_name='inputprompt')
                print(f"Dropped index: {index_name}")
            except Exception as e:
                print(f"Index {index_name} not found or already dropped: {e}")
                pass
    except Exception as e:
        print(f"Index not found or already dropped: {e}")
        pass


def downgrade():
    # Note: We don't recreate the problematic unique constraint in downgrade
    # as it was causing the index size limitation error
    # If you need uniqueness, consider creating a constraint on smaller fields only
    pass 