"""drop deprecated interests and target_industry columns from user_profiles

Revision ID: 20261024_04
Revises: 20261024_03
Create Date: 2026-10-24 03:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "20261024_04"
down_revision = "20261024_03"
branch_labels = None
depends_on = None

def upgrade():
    # Safely drop deprecated columns from user_profiles
    with op.batch_alter_table("user_profiles") as batch_op:
        try:
            batch_op.drop_column("interests")
        except Exception:
            pass
        try:
            batch_op.drop_column("target_industry")
        except Exception:
            pass

def downgrade():
    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.add_column(sa.Column("interests", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("target_industry", sa.String(length=100), nullable=True))
