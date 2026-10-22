from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# --- User Profile Schemas ---
class UserProfileBase(BaseModel):
    name: Optional[str] = None
    education: Optional[str] = None
    current_role: Optional[str] = None
    skills: Optional[str] = None
    interests: Optional[str] = None
    target_industry: Optional[str] = None

class UserProfileCreate(UserProfileBase):
    pass

class UserProfileUpdate(UserProfileBase):
    pass

class UserProfileResponse(UserProfileBase):
    id: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Chat & Context Schemas ---
class ChatMessageSchema(BaseModel):
    role: str
    content: str
    extracted_interests: Optional[str] = None
    career_category: Optional[str] = None
    explanation: Optional[str] = None
    job_titles: Optional[List[str]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class MultiTurnChatRequest(BaseModel):
    user_input: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None

class MultiTurnChatResponse(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    message: str
    interests: List[str] = Field(default_factory=list)
    career_category: Optional[str] = None
    explanation: Optional[str] = None
    job_titles: List[str] = Field(default_factory=list)

class SessionSummaryResponse(BaseModel):
    id: str
    title: str
    created_at: Optional[datetime] = None
    message_count: int = 0

# --- Legacy Request/Response for backward compatibility ---
class CareerRequest(BaseModel):
    user_input: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None

class CareerResponse(BaseModel):
    interests: List[str]
    career_category: str
    explanation: str
    job_titles: List[str]
    session_id: Optional[str] = None
