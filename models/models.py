from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from database import Base

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_input = Column(Text, nullable=False)
    extracted_interests = Column(String, nullable=True)
    career_category = Column(String, nullable=True)
    explanation = Column(Text, nullable=True)
    job_titles = Column(Text, nullable=True)  # Store as comma-separated string
    created_at = Column(DateTime(timezone=True), server_default=func.now())
