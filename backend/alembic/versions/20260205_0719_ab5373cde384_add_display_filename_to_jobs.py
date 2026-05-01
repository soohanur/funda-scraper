"""add_display_filename_to_jobs

Revision ID: ab5373cde384
Revises: 001
Create Date: 2026-02-05 07:19:42.933370+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab5373cde384'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add display_filename column to jobs table
    op.add_column('jobs', sa.Column('display_filename', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove display_filename column from jobs table
    op.drop_column('jobs', 'display_filename')
