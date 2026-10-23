import os
import hmac
import hashlib
import time
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, Request

# Secret used to sign session tokens for verified users
JWT_SECRET = os.getenv("SESSION_SECRET", os.getenv("GROQ_API_KEY", "hirekrkedekho_secure_token_secret_2026"))

def create_access_token(user_id: str, email: str) -> str:
    """
    Create a tamper-proof signed session token (user_id:email:timestamp:signature).
    Does not require external JWT libraries.
    """
    ts = str(int(time.time()))
    payload = f"{user_id}:{email}:{ts}"
    sig = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"

def verify_access_token(token: str, max_age_days: int = 30) -> Optional[Dict[str, str]]:
    """
    Verify signature and expiry of the signed token.
    """
    if not token or ":" not in token:
        return None
    parts = token.split(":")
    if len(parts) != 4:
        return None
    user_id, email, ts_str, signature = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return None

    # Check expiration (default 30 days)
    if time.time() - ts > max_age_days * 86400:
        return None

    payload = f"{user_id}:{email}:{ts_str}"
    expected_sig = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature):
        return None

    return {"user_id": user_id, "email": email}

def get_current_user_from_header(authorization: Optional[str] = Header(None)) -> Dict[str, str]:
    """
    FastAPI dependency to enforce authenticated user token.
    Accepts:
      Authorization: Bearer <signed_token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentication token missing or invalid. Please sign in with Google."
        )
    token = authorization.split("Bearer ")[1].strip()
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(
            status_code=401,
            detail="Session has expired or is invalid. Please sign in again."
        )
    return user_data
