import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
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
        for field in ("education", "current_role", "years_of_experience", "skills", "interests", "target_industry")
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