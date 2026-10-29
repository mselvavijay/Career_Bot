import os
import uuid
import httpx
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models import models
from schemas import schemas

router = APIRouter(prefix="/auth", tags=["Authentication"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

@router.get("/config")
def get_auth_config():
    """Return public OAuth configuration so frontend can initialize Google Sign-In."""
    return {
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", "")
    }

@router.post("/google", response_model=schemas.UserProfileResponse)
async def google_auth(auth_req: schemas.GoogleAuthRequest, db: Session = Depends(get_db)):
    """
    Authenticate user via Google Sign-In token or profile credential.
    Verifies token with Google and creates/fetches the user profile in database.
    """
    google_id = None
    email = None
    name = None
    picture = None

    # Accept only a Google-issued ID token; client-submitted profile fields are not trusted.
    if not auth_req.credential:
        raise HTTPException(status_code=401, detail="Sign in with Google is required.")
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={auth_req.credential}")
        if res.status_code != 200:
            raise HTTPException(status_code=401, detail="Google sign-in could not be verified.")
        data = res.json()
        # Google's token-info endpoint has returned both the string "true" and
        # a boolean true for this field across client/runtime combinations.
        email_verified = data.get("email_verified")
        if data.get("aud") != GOOGLE_CLIENT_ID or email_verified not in (True, "true"):
            raise HTTPException(status_code=401, detail="Google sign-in could not be verified.")
        google_id, email, name, picture = data.get("sub"), data.get("email"), data.get("name"), data.get("picture")
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Google sign-in verification is temporarily unavailable.") from exc
    if not email or not google_id:
        raise HTTPException(status_code=401, detail="Google sign-in could not be verified.")
    # 1. Look up existing user by google_id or email
    user = None
    if google_id:
        user = db.query(models.UserProfile).filter(models.UserProfile.google_id == google_id).first()
    if not user and email:
        user = db.query(models.UserProfile).filter(models.UserProfile.email == email).first()

    if user:
        # Update user profile information if available
        if name and not user.name:
            user.name = name
        if picture:
            user.picture_url = picture
        if google_id and not user.google_id:
            user.google_id = google_id
        if email and not user.email:
            user.email = email
        db.commit()
        db.refresh(user)
    else:
        # Create brand-new profile tied to this Google account
        display_name = name or (email.split("@")[0] if email else "Candidate")
        user = models.UserProfile(
            id=str(uuid.uuid4()),
            email=email,
            google_id=google_id,
            name=display_name,
            picture_url=picture
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    from services.auth_token_service import create_access_token
    user_resp = schemas.UserProfileResponse.model_validate(user)
    user_resp.access_token = create_access_token(user.id, user.email)
    return user_resp

@router.get("/me", response_model=schemas.UserProfileResponse)
def get_current_user(user_id: str = Query(...), db: Session = Depends(get_db)):
    """Retrieve the authenticated user's current profile."""
    user = db.query(models.UserProfile).filter(models.UserProfile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found.")
    return user
