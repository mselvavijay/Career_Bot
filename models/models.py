import uuid
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=True)
    google_id = Column(String(255), unique=True, index=True, nullable=True)
    picture_url = Column(String(500), nullable=True)
    name = Column(String(100), nullable=True)
    education = Column(String(200), nullable=True)
    current_role = Column(String(100), nullable=True)
    years_of_experience = Column(String(50), nullable=True)
    skills = Column(Text, nullable=True)  # Comma-separated or free text
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    sessions = relationship("ConversationSession", back_populates="user", cascade="all, delete-orphan")


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True)
    title = Column(String(200), default="Career Discussion")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("UserProfile", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("conversation_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    # Extra structured response data if role == 'assistant'
    extracted_interests = Column(String(500), nullable=True)
    career_category = Column(String(100), nullable=True)
    explanation = Column(Text, nullable=True)
    job_titles = Column(Text, nullable=True)  # Comma-separated or JSON
    open_jobs = Column(Text, nullable=True)  # JSON-encoded array of structured job listings
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ConversationSession", back_populates="messages")


# Backward compatibility with existing records
class RaceEntry(Base):
    __tablename__ = "race_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    contest_date = Column(String(10), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True)
    razorpay_order_id = Column(String(100), unique=True, nullable=True)
    razorpay_payment_id = Column(String(100), unique=True, nullable=True)
    payment_status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_input = Column(Text, nullable=False)
    extracted_interests = Column(String(500), nullable=True)
    career_category = Column(String(100), nullable=True)
    explanation = Column(Text, nullable=True)
    job_titles = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LLMResponseCache(Base):
    __tablename__ = "llm_response_cache"

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(64), unique=True, index=True, nullable=False)
    response_payload = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), index=True, nullable=False)

class DailyAIUsage(Base):
    __tablename__ = "daily_ai_usage"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    usage_date = Column(String(10), nullable=False)
    fresh_requests = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "usage_date", name="uq_daily_ai_usage_user_date"),)