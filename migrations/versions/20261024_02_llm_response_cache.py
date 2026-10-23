"""add seven day LLM response cache"""
from alembic import op
import sqlalchemy as sa

revision = "20261024_02"
down_revision = "20261024_01"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "llm_response_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("response_payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_llm_response_cache_cache_key", "llm_response_cache", ["cache_key"])
    op.create_index("ix_llm_response_cache_expires_at", "llm_response_cache", ["expires_at"])

def downgrade():
    op.drop_index("ix_llm_response_cache_expires_at", table_name="llm_response_cache")
    op.drop_index("ix_llm_response_cache_cache_key", table_name="llm_response_cache")
    op.drop_table("llm_response_cache")