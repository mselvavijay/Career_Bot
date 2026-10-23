"""create initial career bot schema"""
from alembic import op
import sqlalchemy as sa

revision = "20261024_01"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("user_profiles", sa.Column("id", sa.String(36), primary_key=True), sa.Column("email", sa.String(255), unique=True, index=True), sa.Column("google_id", sa.String(255), unique=True, index=True), sa.Column("picture_url", sa.String(500)), sa.Column("name", sa.String(100)), sa.Column("education", sa.String(200)), sa.Column("current_role", sa.String(100)), sa.Column("years_of_experience", sa.String(50)), sa.Column("skills", sa.Text()), sa.Column("interests", sa.Text()), sa.Column("target_industry", sa.String(100)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_table("conversation_sessions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("user_profiles.id")), sa.Column("title", sa.String(200)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("chat_messages", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.String(36), sa.ForeignKey("conversation_sessions.id"), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("extracted_interests", sa.String(500)), sa.Column("career_category", sa.String(100)), sa.Column("explanation", sa.Text()), sa.Column("job_titles", sa.Text()), sa.Column("open_jobs", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("race_entries", sa.Column("id", sa.String(36), primary_key=True), sa.Column("contest_date", sa.String(10), nullable=False, index=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("user_profiles.id")), sa.Column("razorpay_order_id", sa.String(100), unique=True), sa.Column("razorpay_payment_id", sa.String(100), unique=True), sa.Column("payment_status", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("chat_history", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_input", sa.Text(), nullable=False), sa.Column("extracted_interests", sa.String(500)), sa.Column("career_category", sa.String(100)), sa.Column("explanation", sa.Text()), sa.Column("job_titles", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))

def downgrade():
    op.drop_table("chat_history")
    op.drop_table("race_entries")
    op.drop_table("chat_messages")
    op.drop_table("conversation_sessions")
    op.drop_table("user_profiles")