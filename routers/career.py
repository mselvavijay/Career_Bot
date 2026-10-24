import asyncio
import json
import os
import uuid
from fastapi import Request

# Admin/owner user IDs that are exempt from daily quota — for testing only.
# Set ADMIN_USER_IDS=id1,id2 in .env or Vercel environment variables.
_ADMIN_IDS: set[str] = {
    uid.strip() for uid in os.getenv("ADMIN_USER_IDS", "").split(",") if uid.strip()
}
from services.auth_token_service import get_current_user_from_header, verify_access_token
from services.response_cache import (
    build_cache_key,
    can_make_fresh_request,
    cleanup_expired_conversations,
    get_cached_response,
    get_daily_fresh_requests_count,
    get_target_job_count,
    is_cacheable_question,
    record_fresh_request,
    reserve_daily_fresh_request,
    rollback_daily_fresh_request,
    save_cached_response,
    DAILY_FRESH_REQUEST_LIMIT,
)

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models import models
from schemas import schemas
from services.llm_service import DEFAULT_MODEL, analyze_conversation_turn, analyze_show_more, analyze_user_input
from services.jsearch_service import get_recent_jobs_from_jsearch

router = APIRouter()

# -------------------------------------------------------------
# User Profile Endpoints
# -------------------------------------------------------------

@router.post("/profile", response_model=schemas.UserProfileResponse)
def create_or_update_profile(profile_data: schemas.UserProfileCreate, db: Session = Depends(get_db)):
    """
    Deprecated direct profile creation.
    Profiles must be created via verified Google Sign-In (/auth/google).
    """
    raise HTTPException(
        status_code=401,
        detail="Direct unverified registration is disabled. Please sign in with Google."
    )

@router.put("/profile/{user_id}", response_model=schemas.UserProfileResponse)
def update_profile(
    user_id: str,
    profile_data: schemas.UserProfileUpdate,
    auth_user: dict = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """Update an existing verified user profile. Must be the profile owner."""
    if auth_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot modify another candidate's profile.")

    user = db.query(models.UserProfile).filter(models.UserProfile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")

    update_data = profile_data.model_dump(exclude_unset=True)
    update_data.pop("email", None)
    update_data.pop("google_id", None)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user

@router.get("/profile/{user_id}", response_model=schemas.UserProfileResponse)
def get_profile(
    user_id: str,
    auth_user: dict = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """Retrieve user profile. User can only view their own profile."""
    if auth_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot access another candidate's profile.")

    user = db.query(models.UserProfile).filter(models.UserProfile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")
    return user

@router.delete("/profile/{user_id}")
def delete_account(
    user_id: str,
    auth_user: dict = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """Delete candidate profile and all associated consultations and usage data."""
    if auth_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot delete another candidate's account.")

    user = db.query(models.UserProfile).filter(models.UserProfile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found.")

    # Remove sessions and messages
    sessions = db.query(models.ConversationSession).filter_by(user_id=user_id).all()
    for s in sessions:
        db.query(models.ChatMessage).filter_by(session_id=s.id).delete()
        db.delete(s)
    # Remove daily AI usage
    db.query(models.DailyAIUsage).filter_by(user_id=user_id).delete()
    db.delete(user)
    db.commit()
    return {"status": "success", "message": "Candidate account and consultation data permanently deleted."}

# -------------------------------------------------------------
# Session & Multi-Turn Chat Endpoints
# -------------------------------------------------------------

@router.get("/sessions", response_model=List[schemas.SessionSummaryResponse])
def list_sessions(
    auth_user: dict = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """List recent conversation sessions for the authenticated candidate only."""
    cleanup_expired_conversations(db)

    sessions = (
        db.query(models.ConversationSession)
        .filter(models.ConversationSession.user_id == auth_user["user_id"])
        .order_by(models.ConversationSession.created_at.desc())
        .limit(20)
        .all()
    )

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
def get_session_messages(
    session_id: str,
    auth_user: dict = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """Get full dialogue history for a session. Enforces session ownership."""
    session = db.query(models.ConversationSession).filter(models.ConversationSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.user_id and session.user_id != auth_user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot access another candidate's consultation session.")

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
async def multi_turn_chat(chat_request: schemas.MultiTurnChatRequest, http_request: Request, db: Session = Depends(get_db)):
    """
    Multi-turn career counseling endpoint with profile context & conversation memory.
    Directly uses Groq LLM for guaranteed structured open jobs recommendations.
    user_id is ALWAYS sourced from the verified signed Bearer token — never trusted from the request body.
    """
    user_input = chat_request.user_input.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="Input cannot be empty.")

    # 1. Require a verified signed Bearer token — user_id from the request body is IGNORED
    #    to prevent cross-user quota spoofing.
    auth_header = http_request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Sign in with Google is required to access career consultations."
        )

    token = auth_header.split("Bearer ", 1)[1].strip()
    verified = verify_access_token(token)
    if not verified:
        raise HTTPException(
            status_code=401,
            detail="Authentication token invalid or expired. Please sign in with Google."
        )

    # effective_user_id comes ONLY from the verified token — never from request body
    effective_user_id = verified["user_id"]

    user_profile = db.query(models.UserProfile).filter(models.UserProfile.id == effective_user_id).first()
    if not user_profile:
        raise HTTPException(
            status_code=401,
            detail="Candidate profile not found. Please sign in with Google."
        )

    profile_dict = {
        "name": user_profile.name,
        "education": user_profile.education,
        "current_role": user_profile.current_role,
        "years_of_experience": user_profile.years_of_experience,
        "skills": user_profile.skills
    }

    # 2. Retrieve or create session
    session_id = chat_request.session_id
    if session_id:
        session = db.query(models.ConversationSession).filter(models.ConversationSession.id == session_id).first()
        if not session:
            session = models.ConversationSession(id=session_id, user_id=effective_user_id, title=user_input[:40])
            db.add(session)
            db.commit()
        elif session.user_id and session.user_id != effective_user_id:
            # Prevent session hijacking: token-verified user must own the session
            raise HTTPException(status_code=403, detail="Forbidden: You cannot access another candidate's session.")
    else:
        session = models.ConversationSession(user_id=effective_user_id, title=user_input[:40])
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
    gated_id = effective_user_id or session_id or "anonymous"
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
            user_id=effective_user_id,
            message=gated_reply,
            interests=[],
            career_category="Technology",
            explanation=None,
            job_titles=[],
            open_jobs=[]
        )

    # 5. Atomic check & reservation:
    is_admin = effective_user_id in _ADMIN_IDS  # admins skip quota entirely

    session_jobs_turns = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.session_id == session_id,
            models.ChatMessage.role == "assistant",
            models.ChatMessage.open_jobs.isnot(None),
            models.ChatMessage.open_jobs != "[]"
        )
        .count()
    )
    current_fresh_count = get_daily_fresh_requests_count(db, models.DailyAIUsage, effective_user_id)
    # Admins always get 4 jobs per request regardless of daily usage
    target_job_count = 4 if is_admin else get_target_job_count(current_fresh_count, session_jobs_turns)

    # Check cache first (cached responses don't debit daily quota)
    cache_key = None
    llm_result = None
    if not conversation_history and is_cacheable_question(user_input):
        cache_key = build_cache_key(user_input, profile_dict, DEFAULT_MODEL)
        llm_result = get_cached_response(db, models.LLMResponseCache, cache_key)

    if llm_result is None:
        if is_admin:
            # Admins bypass atomic quota reservation — their requests are never counted
            reserved = True
        else:
            # Atomic single-statement reservation (WHERE fresh_requests < 3 UPDATE fresh_requests = fresh_requests + 1)
            # Prevents race conditions from simultaneous parallel clicks
            reserved = reserve_daily_fresh_request(db, models.DailyAIUsage, effective_user_id)
        if not is_admin and (not reserved or target_job_count == 0):
            limit_reply = "Daily limit reached. Come back tomorrow for new openings."
            assistant_msg = models.ChatMessage(
                session_id=session_id,
                role="assistant",
                content=limit_reply,
                extracted_interests="",
                career_category="Professional & Technology",
                explanation=limit_reply,
                job_titles="",
                open_jobs="[]"
            )
            db.add(assistant_msg)
            db.commit()

            return schemas.MultiTurnChatResponse(
                session_id=session_id,
                user_id=effective_user_id,
                message=limit_reply,
                interests=[],
                career_category="Professional & Technology",
                explanation=limit_reply,
                job_titles=[],
                open_jobs=[],
                remaining_requests=0,
                daily_limit_reached=True,
                open_jobs_today=8
            )

        try:
            if session_jobs_turns > 0:
                past_assistant_msgs = (
                    db.query(models.ChatMessage)
                    .filter(
                        models.ChatMessage.session_id == session_id,
                        models.ChatMessage.role == "assistant",
                        models.ChatMessage.job_titles.isnot(None),
                        models.ChatMessage.job_titles != ""
                    )
                    .all()
                )
                excluded_titles: List[str] = []
                for msg in past_assistant_msgs:
                    excluded_titles.extend([t.strip() for t in msg.job_titles.split(" || ") if t.strip()])

                llm_result = await analyze_show_more(
                    user_input=user_input,
                    excluded_titles=excluded_titles,
                    user_profile=profile_dict,
                    target_job_count=target_job_count
                )
            else:
                llm_result = await analyze_conversation_turn(
                    user_input=user_input,
                    conversation_history=conversation_history,
                    user_profile=profile_dict,
                    target_job_count=target_job_count
                )
            if cache_key:
                save_cached_response(db, models.LLMResponseCache, cache_key, llm_result)
        except Exception as e:
            # Automatic failure refund: if Groq or downstream fails, quota is not charged
            rollback_daily_fresh_request(db, models.DailyAIUsage, effective_user_id)
            raise e

    current_fresh_count = get_daily_fresh_requests_count(db, models.DailyAIUsage, effective_user_id)

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
        user_id=effective_user_id,
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
async def career_bot(request: schemas.CareerRequest, http_request: Request, db: Session = Depends(get_db)):
    multi_turn_res = await multi_turn_chat(
        schemas.MultiTurnChatRequest(
            user_input=request.user_input,
            session_id=request.session_id,
            user_id=request.user_id
        ),
        http_request=http_request,
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

