from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv

load_dotenv()

# Use PostgreSQL if DATABASE_URL is set; otherwise SQLite
raw_db_url = os.getenv("DATABASE_URL", "")
is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

if raw_db_url:
    # Normalize Supabase/Postgres URLs to the psycopg2 driver included with this project.
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif raw_db_url.startswith("postgresql+psycopg://"):
        raw_db_url = raw_db_url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    elif raw_db_url.startswith("postgresql://"):
        raw_db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    SQLALCHEMY_DATABASE_URL = raw_db_url
else:
    # If on serverless platforms (e.g. Vercel), write to /tmp for ephemeral writable access
    is_serverless = os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    db_path = "/tmp/career_bot.db" if is_serverless else "./career_bot.db"
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine_options = {"connect_args": connect_args}
# Serverless functions must return each connection to Supabase's transaction pool after the request.
if is_serverless and not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_options["poolclass"] = NullPool

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables and apply safe schema migrations for both SQLite and PostgreSQL."""
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine)

    # Safely ensure new columns exist in existing tables
    migrations = [
        ("user_profiles", "email", "VARCHAR(255)"),
        ("user_profiles", "google_id", "VARCHAR(255)"),
        ("user_profiles", "picture_url", "VARCHAR(500)"),
        ("user_profiles", "years_of_experience", "VARCHAR(50)"),
        ("chat_messages", "open_jobs", "TEXT"),
    ]

    with engine.begin() as conn:
        for table, col, col_type in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
            except Exception:
                # Column likely already exists or database engine handled it
                pass

        # Safely drop deprecated legacy columns from user_profiles if present
        for col in ("interests", "target_industry"):
            try:
                conn.execute(text(f"ALTER TABLE user_profiles DROP COLUMN {col}"))
            except Exception:
                pass

    # Automatically purge conversations older than 30 days & expired cache on startup
    try:
        from services.response_cache import cleanup_expired_conversations
        cleanup_db = SessionLocal()
        try:
            cleanup_expired_conversations(cleanup_db)
        finally:
            cleanup_db.close()
    except Exception as e:
        print(f"Notice during startup retention cleanup: {e}")


