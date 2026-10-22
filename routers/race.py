import hashlib
import hmac
import os
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.models import RaceEntry

router = APIRouter(prefix="/race", tags=["AI Race"])
MAX_RACE_ENTRANTS = 20


class RaceOrderRequest(BaseModel):
    user_id: str | None = None


class RacePaymentVerification(BaseModel):
    entry_id: str
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


def payment_settings() -> tuple[str, str, int]:
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    try:
        fee_paise = int(os.getenv("RACE_ENTRY_FEE_PAISE", "0"))
    except ValueError:
        fee_paise = 0
    if not key_id or not key_secret or fee_paise < 100:
        raise HTTPException(status_code=503, detail="Race payments are not configured. Add Razorpay keys and RACE_ENTRY_FEE_PAISE.")
    return key_id, key_secret, fee_paise


@router.get("/status")
def race_status(db: Session = Depends(get_db)):
    today = date.today().isoformat()
    booked = db.query(RaceEntry).filter(RaceEntry.contest_date == today).count()
    return {"contest_date": today, "capacity": MAX_RACE_ENTRANTS, "booked": booked, "seats_left": max(0, MAX_RACE_ENTRANTS - booked)}


@router.post("/orders")
async def create_race_order(payload: RaceOrderRequest, db: Session = Depends(get_db)):
    key_id, key_secret, fee_paise = payment_settings()
    today = date.today().isoformat()
    booked = db.query(RaceEntry).filter(RaceEntry.contest_date == today).count()
    if booked >= MAX_RACE_ENTRANTS:
        raise HTTPException(status_code=409, detail="Today's AI Race is full.")

    entry = RaceEntry(contest_date=today, user_id=payload.user_id, payment_status="pending")
    db.add(entry)
    db.commit()
    db.refresh(entry)

    order_payload = {"amount": fee_paise, "currency": "INR", "receipt": f"race_{entry.id[:16]}", "notes": {"race_entry_id": entry.id, "contest_date": today}}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post("https://api.razorpay.com/v1/orders", json=order_payload, auth=(key_id, key_secret))
            response.raise_for_status()
            order = response.json()
    except httpx.HTTPError as exc:
        db.delete(entry)
        db.commit()
        raise HTTPException(status_code=502, detail="Unable to create Razorpay order.") from exc

    entry.razorpay_order_id = order["id"]
    db.commit()
    return {"entry_id": entry.id, "key_id": key_id, "order_id": order["id"], "amount": order["amount"], "currency": "INR", "seats_left": MAX_RACE_ENTRANTS - booked - 1}



class RaceEntryCancellation(BaseModel):
    entry_id: str


@router.post("/cancel")
def cancel_race_entry(payload: RaceEntryCancellation, db: Session = Depends(get_db)):
    entry = db.query(RaceEntry).filter(RaceEntry.id == payload.entry_id, RaceEntry.payment_status == "pending").first()
    if entry:
        db.delete(entry)
        db.commit()
    return {"status": "released"}@router.post("/verify")
def verify_race_payment(payload: RacePaymentVerification, db: Session = Depends(get_db)):
    _, key_secret, _ = payment_settings()
    entry = db.query(RaceEntry).filter(RaceEntry.id == payload.entry_id, RaceEntry.razorpay_order_id == payload.razorpay_order_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Race entry not found.")
    expected = hmac.new(key_secret.encode(), f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, payload.razorpay_signature):
        raise HTTPException(status_code=400, detail="Payment verification failed.")
    entry.razorpay_payment_id = payload.razorpay_payment_id
    entry.payment_status = "paid"
    db.commit()
    return {"status": "paid", "entry_id": entry.id}
