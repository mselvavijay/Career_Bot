import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

CACHE_TTL = timedelta(days=7)
CACHE_PROMPT_VERSION = "career-v1"
TIME_SENSITIVE_PATTERNS = (
    "today", "tomorrow", "latest", "current", "newest", "this week",
    "recent", "live opening", "openings today", "contest", "salary today",
)


def is_cacheable_question(question: str) -> bool:
    normalized = " ".join(question.lower().split())
    return bool(normalized) and not any(term in normalized for term in TIME_SENSITIVE_PATTERNS)


def build_cache_key(question: str, profile: Optional[Dict[str, Any]], model_name: str) -> str:
    normalized_question = " ".join(question.lower().split())
    profile_context = {
        field: (profile or {}).get(field) or ""
        for field in ("education", "current_role", "years_of_experience", "skills")
    }
    payload = json.dumps(
        {"question": normalized_question, "profile": profile_context, "model": model_name, "prompt": CACHE_PROMPT_VERSION},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cached_response(db, cache_model, cache_key: str) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    entry = db.query(cache_model).filter(cache_model.cache_key == cache_key, cache_model.expires_at > now).first()
    if not entry:
        return None
    try:
        return json.loads(entry.response_payload)
    except (TypeError, ValueError):
        return None


def save_cached_response(db, cache_model, cache_key: str, response: Dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    db.query(cache_model).filter(cache_model.expires_at <= now).delete(synchronize_session=False)
    entry = cache_model(cache_key=cache_key, response_payload=json.dumps(response), expires_at=now + CACHE_TTL)
    db.add(entry)
    db.commit()
DAILY_FRESH_REQUEST_LIMIT = 3
CONVERSATION_RETENTION_DAYS = 30
IST = timezone(timedelta(hours=5, minutes=30))

def get_today_ist() -> str:
    """Return today's date in Indian Standard Time (IST, UTC+05:30) so daily quotas reset at midnight in India."""
    return datetime.now(IST).date().isoformat()

def get_daily_fresh_requests_count(db, usage_model, user_id: Optional[str]) -> int:
    """Return the number of fresh AI consultations made by the candidate today."""
    if not user_id:
        return 0
    today = get_today_ist()
    usage = db.query(usage_model).filter_by(user_id=user_id, usage_date=today).first()
    return usage.fresh_requests if usage else 0

def can_make_fresh_request(db, usage_model, user_id: Optional[str]) -> bool:
    """Check if candidate has not exceeded their 3 fresh AI consultations for the day."""
    return get_daily_fresh_requests_count(db, usage_model, user_id) < DAILY_FRESH_REQUEST_LIMIT

def get_target_job_count(fresh_requests_used: int, session_jobs_count: Optional[int] = None) -> int:
    """
    Candidate Free-Tier Plan (4 + 2 + 2 Model):
    - 1st request (Initial consultation, 0 used prior): 4 job openings
    - 2nd request (1st 'Show more', 1 used prior): 2 additional job openings
    - 3rd request (2nd 'Show more', 2 used prior): 2 additional job openings
    Total: 8 job openings per candidate per day across 3 requests.
    """
    if fresh_requests_used >= DAILY_FRESH_REQUEST_LIMIT:
        return 0
    if session_jobs_count is not None:
        if session_jobs_count == 0:
            return 4
        elif session_jobs_count in (1, 2):
            return 2
        return 0
    if fresh_requests_used <= 0:
        return 4
    elif fresh_requests_used in (1, 2):
        return 2
    return 0

def record_fresh_request(db, usage_model, user_id: Optional[str]) -> int:
    """Record a fresh AI request and return the updated count for today."""
    if not user_id:
        return 1
    
    from models import models
    user_exists = db.query(models.UserProfile.id).filter_by(id=user_id).first()
    if not user_exists:
        return 1

    today = get_today_ist()
    usage = db.query(usage_model).filter_by(user_id=user_id, usage_date=today).first()
    if usage:
        usage.fresh_requests += 1
        new_count = usage.fresh_requests
    else:
        new_count = 1
        db.add(usage_model(user_id=user_id, usage_date=today, fresh_requests=1))
    db.commit()
    return new_count

def cleanup_expired_conversations(db) -> dict:
    """
    Enforce 30-day retention period on conversation history to recover Supabase / database space.
    - Candidates can revisit recent consultations within 30 days.
    - Old conversation sessions and their chat messages are automatically deleted after 30 days.
    - AI response cache remains 7 days (cleans expired entries).
    - User Profiles remain PERMANENT and are never purged.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=CONVERSATION_RETENTION_DAYS)
    
    cleaned_sessions = 0
    try:
        from models import models
        # Find expired sessions older than 30 days
        expired_sessions = db.query(models.ConversationSession).filter(
            models.ConversationSession.created_at < cutoff
        ).all()
        cleaned_sessions = len(expired_sessions)
        for s in expired_sessions:
            db.delete(s)
            
        # Clean legacy chat_history older than 30 days
        db.query(models.ChatHistory).filter(
            models.ChatHistory.created_at < cutoff
        ).delete(synchronize_session=False)

        # Clean AI response cache older than 7 days
        db.query(models.LLMResponseCache).filter(
            models.LLMResponseCache.expires_at <= now
        ).delete(synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        # Non-blocking cleanup logger
        print(f"Notice during conversation retention cleanup: {e}")

    return {"cleaned_sessions": cleaned_sessions, "cutoff": cutoff.isoformat()}