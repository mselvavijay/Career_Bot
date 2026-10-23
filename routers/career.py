import asyncio
import json
import uuid
from services.response_cache import (
    build_cache_key,
    can_make_fresh_request,
    cleanup_expired_conversations,
    get_cached_response,
    get_daily_fresh_requests_count,
    get_target_job_count,
    is_cacheable_question,
    record_fresh_request,
    save_cached_response,
    DAILY_FRESH_REQUEST_LIMIT,
)
from services.llm_service import DEFAULT_MODEL
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models import models
from schemas import schemas
from services.llm_service import analyze_conversation_turn, analyze_user_input
from services.jsearch_service import get_recent_jobs_from_jsearch

router = APIRouter()

# -------------------------------------------------------------
# User Profile Endpoints
# -------------------------------------------------------------

@router.post("/profile", response_model=schemas.UserProfileResponse)
def create_or_update_profile(profile_data: schemas.UserProfileCreate, db: Session = Depends(get_db)):
    """Create a new user profile or initialize one."""
    new_user = models.UserProfile(
        name=profile_data.name,
        email=profile_data.email,
        picture_url=profile_data.picture_url,
        google_id=profile_data.google_id,
        education=profile_data.education,
        current_role=profile_data.current_role,
        years_of_experience=profile_data.years_of_experience,
        skills=profile_data.skills
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.put("/profile/{user_id}", response_model=schemas.UserProfileResponse)
def update_profile(user_id: str, profile_data: schemas.UserProfileUpdate, db: Session = Depends(get_db)):
    """Update an existing user profile."""
    user = db.query(models.UserProfile).filter(models.UserProfile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")

    for field, value in profile_data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user

@router.get("/profile/{user_id}", response_model=schemas.UserProfileResponse)
def get_profile(user_id: str, db: Session = Depends(get_db)):
    """Retrieve an existing user profile."""
    user = db.query(models.UserProfile).filter(models.UserProfile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")
    return user


# -------------------------------------------------------------
# Session & Multi-Turn Chat Endpoints
# -------------------------------------------------------------

@router.get("/sessions", response_model=List[schemas.SessionSummaryResponse])
def list_sessions(user_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """List recent conversation sessions (within 30-day retention window)."""
    # Enforce 30-day retention cleanup on Supabase / database storage
    cleanup_expired_conversations(db)

    query = db.query(models.ConversationSession)
    if user_id:
        query = query.filter(models.ConversationSession.user_id == user_id)
    sessions = query.order_by(models.ConversationSession.created_at.desc()).limit(20).all()

    result = []
    for s in sessions:
        msg_count = db.query(models.ChatMessage).filter(models.ChatMessage.session_id == s.id).count()
        result.append(schemas.SessionSummaryResponse(
            id=s.id,
            title=s.title or "Career Discussion",
            created_at=s.created_at,
            message_count=msg_count
        ))
    return result

@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, db: Session = Depends(get_db)):
    """Get full dialogue history for a session."""
    session = db.query(models.ConversationSession).filter(models.ConversationSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )

    output = []
    for m in messages:
        open_jobs_data = []
        if m.open_jobs:
            try:
                open_jobs_data = json.loads(m.open_jobs)
            except Exception:
                open_jobs_data = []

        output.append({
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "extracted_interests": m.extracted_interests.split(",") if m.extracted_interests else [],
            "career_category": m.career_category,
            "explanation": m.explanation,
            "job_titles": m.job_titles.split(" || ") if m.job_titles else [],
            "open_jobs": open_jobs_data,
            "created_at": m.created_at
        })
    return output


@router.post("/chat", response_model=schemas.MultiTurnChatResponse)
async def multi_turn_chat(request: schemas.MultiTurnChatRequest, db: Session = Depends(get_db)):
    """
    Multi-turn career counseling endpoint with profile context & conversation memory.
    Directly uses Groq LLM for guaranteed structured open jobs recommendations.
    """
    user_input = request.user_input.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="Input cannot be empty.")

    # 1. Retrieve or initialize user profile if user_id is provided
    profile_dict = None
    if request.user_id:
        user_profile = db.query(models.UserProfile).filter(models.UserProfile.id == request.user_id).first()
        if user_profile:
            profile_dict = {
                "name": user_profile.name,
                "education": user_profile.education,
                "current_role": user_profile.current_role,
                "years_of_experience": user_profile.years_of_experience,
                "skills": user_profile.skills
            }

    # 2. Retrieve or create session
    session_id = request.session_id
    if session_id:
        session = db.query(models.ConversationSession).filter(models.ConversationSession.id == session_id).first()
        if not session:
            session = models.ConversationSession(id=session_id, user_id=request.user_id, title=user_input[:40])
            db.add(session)
            db.commit()
    else:
        session = models.ConversationSession(user_id=request.user_id, title=user_input[:40])
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

    # 3. Fetch past messages for this session (context memory)
    past_db_messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )
    conversation_history = [{"role": m.role, "content": m.content + (f"\nPreviously suggested roles: {m.job_titles}" if m.role == "assistant" and m.job_titles else "")} for m in past_db_messages]

    # Save incoming user message
    user_msg_record = models.ChatMessage(session_id=session_id, role="user", content=user_input)
    db.add(user_msg_record)
    db.commit()

    # 4. STEP 1 - 4: Message-Gating Layer & Topic Guardrails (Rule-based, instant, $0 cost)
    from services.guardrail_service import run_guardrails_pipeline
    gated_id = request.user_id or session_id or "anonymous"
    should_stop, gated_reply, stage = run_guardrails_pipeline(user_input, gated_id)

    if should_stop and gated_reply:
        # Save guarded assistant turn (no LLM call, no job search, clean consistent thread)
        assistant_msg = models.ChatMessage(
            session_id=session_id,
            role="assistant",
            content=gated_reply,
            extracted_interests="",
            career_category="Technology",
            explanation=None,
            job_titles="",
            open_jobs="[]"
        )
        db.add(assistant_msg)
        db.commit()

        return schemas.MultiTurnChatResponse(
            session_id=session_id,
            user_id=request.user_id,
            message=gated_reply,
            interests=[],
            career_category="Technology",
            explanation=None,
            job_titles=[],
            open_jobs=[]
        )

    # 5. Reuse a profile-aware response for standalone, non-time-sensitive questions.
    # Contextual follow-ups always use the LLM because earlier messages change their meaning.
    cache_key = None
    llm_result = None
    current_fresh_count = get_daily_fresh_requests_count(db, models.DailyAIUsage, request.user_id)
    target_job_count = get_target_job_count(current_fresh_count)

    if not conversation_history and is_cacheable_question(user_input):
        cache_key = build_cache_key(user_input, profile_dict, DEFAULT_MODEL)
        llm_result = get_cached_response(db, models.LLMResponseCache, cache_key)

    if llm_result is None:
        if current_fresh_count >= DAILY_FRESH_REQUEST_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Daily limit reached. Come back tomorrow for new openings."
            )
        llm_result = await analyze_conversation_turn(
            user_input=user_input,
            conversation_history=conversation_history,
            user_profile=profile_dict,
            target_job_count=target_job_count
        )
        current_fresh_count = record_fresh_request(db, models.DailyAIUsage, request.user_id)
        if cache_key:
            save_cached_response(db, models.LLMResponseCache, cache_key, llm_result)

    reply_text = llm_result.get("reply") or llm_result.get("explanation") or "Here are your career recommendations."
    interests_list = llm_result.get("interests", [])
    career_category = llm_result.get("career_category", "Professional & Technology")
    explanation = llm_result.get("explanation", "")
    llm_job_titles = llm_result.get("job_titles", [])
    raw_open_jobs = llm_result.get("open_jobs", [])

    # Prefer live India listings posted within the past week when JSearch is configured.
    recent_jobs = await get_recent_jobs_from_jsearch(llm_job_titles)
    if recent_jobs:
        raw_open_jobs = recent_jobs

    # Convert to structured JobListing schemas
    structured_jobs: List[schemas.JobListing] = []
    for item in raw_open_jobs:
        if isinstance(item, dict):
            structured_jobs.append(schemas.JobListing(**item))
        elif isinstance(item, schemas.JobListing):
            structured_jobs.append(item)

    # Free-tier calibration: exactly target_job_count (4 on fresh initial, 2 on 1st show more, 2 on 2nd show more)
    structured_jobs = structured_jobs[:target_job_count]
    final_job_titles = [j.title for j in structured_jobs] or llm_job_titles[:target_job_count]

    # 5. Save assistant turn to database (including open_jobs JSON)
    open_jobs_json = json.dumps([j.model_dump() for j in structured_jobs])
    assistant_msg = models.ChatMessage(
        session_id=session_id,
        role="assistant",
        content=reply_text,
        extracted_interests=",".join(interests_list),
        career_category=career_category,
        explanation=explanation,
        job_titles=" || ".join(final_job_titles),
        open_jobs=open_jobs_json
    )
    db.add(assistant_msg)

    # Also keep legacy ChatHistory in sync
    db_history = models.ChatHistory(
        user_input=user_input,
        extracted_interests=",".join(interests_list),
        career_category=career_category,
        explanation=explanation,
        job_titles=",".join(final_job_titles)
    )
    db.add(db_history)
    db.commit()

    remaining_requests = max(0, DAILY_FRESH_REQUEST_LIMIT - current_fresh_count)
    daily_limit_reached = (remaining_requests == 0)
    openings_today = 4 if current_fresh_count == 1 else (6 if current_fresh_count == 2 else (8 if current_fresh_count >= 3 else len(structured_jobs)))

    return schemas.MultiTurnChatResponse(
        session_id=session_id,
        user_id=request.user_id,
        message=reply_text,
        interests=interests_list,
        career_category=career_category,
        explanation=explanation,
        job_titles=final_job_titles,
        open_jobs=structured_jobs,
        remaining_requests=remaining_requests,
        daily_limit_reached=daily_limit_reached,
        open_jobs_today=openings_today
    )


# -------------------------------------------------------------
# Legacy Endpoint: /career-bot (Maintained for backwards compatibility)
# -------------------------------------------------------------
@router.post("/career-bot", response_model=schemas.CareerResponse)
async def career_bot(request: schemas.CareerRequest, db: Session = Depends(get_db)):
    multi_turn_res = await multi_turn_chat(
        schemas.MultiTurnChatRequest(
            user_input=request.user_input,
            session_id=request.session_id,
            user_id=request.user_id
        ),
        db=db
    )
    return schemas.CareerResponse(
        interests=multi_turn_res.interests,
        career_category=multi_turn_res.career_category or "STEM",
        explanation=multi_turn_res.explanation or multi_turn_res.message,
        job_titles=multi_turn_res.job_titles,
        open_jobs=multi_turn_res.open_jobs,
        session_id=multi_turn_res.session_id
    )

