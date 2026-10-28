"""Add AI Race tables and user_profiles.display_name column.

Revision ID: 20261027_01
Revises: 20261024_04
Create Date: 2026-10-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20261027_01"
down_revision = "20261024_04"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in cols


def upgrade():
    conn = op.get_context().connection

    # --- user_profiles.display_name (safe if already exists) ---
    if _table_exists(conn, "user_profiles") and not _column_exists(conn, "user_profiles", "display_name"):
        with op.batch_alter_table("user_profiles") as batch_op:
            batch_op.add_column(sa.Column("display_name", sa.String(length=30), nullable=True))

    # --- race_daily_quizzes ---
    if not _table_exists(conn, "race_daily_quizzes"):
        op.create_table(
            "race_daily_quizzes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contest_date", sa.String(length=10), unique=True, nullable=False, index=True),
            sa.Column("theme", sa.String(length=100), nullable=False),
            sa.Column("questions_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # --- race_attempts ---
    if not _table_exists(conn, "race_attempts"):
        op.create_table(
            "race_attempts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("contest_date", sa.String(length=10), nullable=False, index=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("user_profiles.id"), nullable=False),
            sa.Column("display_name", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="in_progress"),
            sa.Column("current_question", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_time_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("question_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("contest_date", "user_id", name="uq_race_attempt_user_day"),
        )

    # --- race_answers ---
    if not _table_exists(conn, "race_answers"):
        op.create_table(
            "race_answers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("attempt_id", sa.String(length=36), sa.ForeignKey("race_attempts.id"), nullable=False, index=True),
            sa.Column("question_index", sa.Integer(), nullable=False),
            sa.Column("selected_index", sa.Integer(), nullable=False),
            sa.Column("is_correct", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("elapsed_ms", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("attempt_id", "question_index", name="uq_race_answer_once"),
        )

    # --- race_winners ---
    if not _table_exists(conn, "race_winners"):
        op.create_table(
            "race_winners",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contest_date", sa.String(length=10), unique=True, nullable=False, index=True),
            sa.Column("attempt_id", sa.String(length=36), sa.ForeignKey("race_attempts.id"), nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("user_profiles.id"), nullable=False),
            sa.Column("certificate_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # --- race_question_archive ---
    if not _table_exists(conn, "race_question_archive"):
        op.create_table(
            "race_question_archive",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contest_date", sa.String(length=10), nullable=False, index=True),
            sa.Column("question_hash", sa.String(length=64), unique=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade():
    conn = op.get_context().connection

    # Drop in reverse dependency order
    if _table_exists(conn, "race_question_archive"):
        op.drop_table("race_question_archive")
    if _table_exists(conn, "race_winners"):
        op.drop_table("race_winners")
    if _table_exists(conn, "race_answers"):
        op.drop_table("race_answers")
    if _table_exists(conn, "race_attempts"):
        op.drop_table("race_attempts")
    if _table_exists(conn, "race_daily_quizzes"):
        op.drop_table("race_daily_quizzes")

    # Remove display_name column from user_profiles
    if _table_exists(conn, "user_profiles") and _column_exists(conn, "user_profiles", "display_name"):
        with op.batch_alter_table("user_profiles") as batch_op:
            batch_op.drop_column("display_name")