from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- User Profile Schemas ---
class UserProfileBase(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    picture_url: Optional[str] = None
    education: Optional[str] = None
    current_role: Optional[str] = None
    years_of_experience: Optional[str] = None
    skills: Optional[str] = None
    interests: Optional[str] = None
    target_industry: Optional[str] = None

class UserProfileCreate(UserProfileBase):
    google_id: Optional[str] = None

class UserProfileUpdate(UserProfileBase):
    pass

class UserProfileResponse(UserProfileBase):
    id: str
    google_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Auth Schemas ---
class GoogleAuthRequest(BaseModel):
    credential: Optional[str] = None  # Google ID Token
    email: Optional[str] = None
    name: Optional[str] = None
    google_id: Optional[str] = None
    picture: Optional[str] = None


# --- Structured Job Listing Schemas ---
class JobListing(BaseModel):
    title: str
    company: str = "Top Tech India"
    location: str = "Bangalore / Remote India"
    job_type: str = "Full-time"
    salary_range: Optional[str] = None
    skills_required: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    prep_guide: Optional[List[str]] = Field(default_factory=list)
    apply_url: Optional[str] = None


# --- Chat & Context Schemas ---
class ChatMessageSchema(BaseModel):
    role: str
    content: str
    extracted_interests: Optional[str] = None
    career_category: Optional[str] = None
    explanation: Optional[str] = None
    job_titles: Optional[List[str]] = None
    open_jobs: Optional[List[JobListing]] = None
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
    open_jobs: List[JobListing] = Field(default_factory=list)
    remaining_requests: Optional[int] = None
    daily_limit_reached: Optional[bool] = False
    open_jobs_today: Optional[int] = None

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
    open_jobs: List[JobListing] = Field(default_factory=list)
    session_id: Optional[str] = None

