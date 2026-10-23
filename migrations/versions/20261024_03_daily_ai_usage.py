"""add daily AI usage limits"""
from alembic import op
import sqlalchemy as sa
revision = "20261024_03"
down_revision = "20261024_02"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("daily_ai_usage", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.String(length=36), sa.ForeignKey("user_profiles.id"), nullable=False), sa.Column("usage_date", sa.String(length=10), nullable=False), sa.Column("fresh_requests", sa.Integer(), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("user_id", "usage_date", name="uq_daily_ai_usage_user_date"))

def downgrade():
    op.drop_table("daily_ai_usage")