import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import get_db
from models.models import UserProfile, RaceAttempt, RaceAnswer, RaceWinner, RaceDailyQuiz
from services.auth_token_service import get_current_user_from_header
from services.race_service import contest_date, create_daily_quiz, decide_winner, leaderboard, now_ist, public_name, questions_for_player, QUESTION_SECONDS, GRACE_SECONDS

router = APIRouter(prefix="/race", tags=["AI Race"])
ADMIN_EMAILS = {email.strip().lower() for email in os.getenv("ADMIN_EMAILS", "").split(",") if email.strip()}
class AnswerRequest(BaseModel): question_index: int = Field(ge=0, le=14); option_index: int = Field(ge=-1, le=3)
class DisplayNameRequest(BaseModel): display_name: str

def user_from_token(token, db):
    user = db.query(UserProfile).filter_by(id=token["user_id"], email=token["email"]).first()
    if not user: raise HTTPException(401, "Sign in with Google to continue.")
    return user

def require_admin(token):
    if not ADMIN_EMAILS or token["email"].lower() not in ADMIN_EMAILS: raise HTTPException(403, "Admin access required.")

@router.get("/today")
async def today(db: Session = Depends(get_db), token=Depends(get_current_user_from_header)):
    user = user_from_token(token, db); day = contest_date(); quiz = await create_daily_quiz(db, day)
    attempt = db.query(RaceAttempt).filter_by(contest_date=day, user_id=user.id).first()
    return {"contest_date": day, "theme": quiz.theme, "question_count": 15, "seconds_per_question": QUESTION_SECONDS, "grace_seconds": GRACE_SECONDS, "attempt_status": attempt.status if attempt else "not_started", "leaderboard": leaderboard(db, day)[:10]}

@router.post("/start")
async def start(db: Session = Depends(get_db), token=Depends(get_current_user_from_header)):
    user = user_from_token(token, db); day = contest_date(); quiz = await create_daily_quiz(db, day)
    attempt = db.query(RaceAttempt).filter_by(contest_date=day, user_id=user.id).first()
    if attempt and attempt.status == "completed": raise HTTPException(409, "You have already completed todays contest.")
    if not attempt:
        name = public_name(getattr(user, "display_name", None) or (user.email or "").split("@")[0])
        attempt = RaceAttempt(contest_date=day, user_id=user.id, display_name=name, status="in_progress", current_question=0, question_started_at=now_ist())
        db.add(attempt); db.commit(); db.refresh(attempt)
    return {"attempt_id": attempt.id, "questions": questions_for_player(quiz), "current_question": attempt.current_question, "expires_in_seconds": QUESTION_SECONDS + GRACE_SECONDS}

@router.post("/answer")
async def answer(payload: AnswerRequest, db: Session = Depends(get_db), token=Depends(get_current_user_from_header)):
    user = user_from_token(token, db); day = contest_date(); attempt = db.query(RaceAttempt).filter_by(contest_date=day, user_id=user.id).first()
    if not attempt or attempt.status != "in_progress": raise HTTPException(409, "No active contest attempt.")
    if payload.question_index != attempt.current_question: raise HTTPException(409, "That question is no longer active.")
    elapsed = int((now_ist() - attempt.question_started_at).total_seconds() * 1000)
    quiz = db.query(__import__('models.models', fromlist=['RaceDailyQuiz']).RaceDailyQuiz).filter_by(contest_date=day).first(); question = __import__('json').loads(quiz.questions_json)[payload.question_index]
    correct = elapsed <= (QUESTION_SECONDS + GRACE_SECONDS) * 1000 and payload.option_index >= 0 and payload.option_index == question["answer_index"]
    db.add(RaceAnswer(attempt_id=attempt.id, question_index=payload.question_index, selected_index=payload.option_index, is_correct=correct, elapsed_ms=elapsed))
    attempt.score += int(correct); attempt.total_time_ms += min(elapsed, (QUESTION_SECONDS + GRACE_SECONDS) * 1000); attempt.current_question += 1
    if attempt.current_question >= 15: attempt.status="completed"; attempt.completed_at=now_ist()
    else: attempt.question_started_at=now_ist()
    db.commit()
    return {"correct": None, "completed": attempt.status == "completed", "score": attempt.score, "next_question": attempt.current_question}

@router.get("/leaderboard")
def board(db: Session = Depends(get_db)):
    return {"contest_date": contest_date(), "entries": leaderboard(db, contest_date())}

@router.get("/winner/latest")
def latest_winner(db: Session = Depends(get_db), token=Depends(get_current_user_from_header)):
    user = user_from_token(token, db); yesterday = (now_ist().date().fromordinal(now_ist().date().toordinal()-1)).isoformat(); winner = decide_winner(db, yesterday)
    if not winner: return {"winner": None}
    attempt = db.query(RaceAttempt).filter_by(id=winner.attempt_id).first(); result={"contest_date": yesterday, "display_name": attempt.display_name, "score": attempt.score, "total_time_ms": attempt.total_time_ms}
    if winner.user_id == user.id: result["real_name"] = user.name; result["is_you"] = True
    return {"winner": result}

@router.put("/display-name")
def display_name(payload: DisplayNameRequest, db: Session = Depends(get_db), token=Depends(get_current_user_from_header)):
    user=user_from_token(token, db); user.display_name=public_name(payload.display_name); db.commit(); return {"display_name": user.display_name}

@router.get("/admin/leaderboard")
def admin_leaderboard(db: Session = Depends(get_db), token=Depends(get_current_user_from_header)):
    require_admin(token); return {"contest_date": contest_date(), "entries": leaderboard(db, contest_date())}

@router.get("/admin/day")
def admin_day(date_value: str | None = None, db: Session = Depends(get_db), token=Depends(get_current_user_from_header)):
    """Private daily audit: questions, submitted answers, ranking, and winner contact details."""
    require_admin(token)
    day = date_value or contest_date()
    quiz = db.query(RaceDailyQuiz).filter_by(contest_date=day).first()
    attempts = db.query(RaceAttempt).filter_by(contest_date=day, status="completed").order_by(RaceAttempt.score.desc(), RaceAttempt.total_time_ms.asc(), RaceAttempt.completed_at.asc()).all()
    rows = []
    for rank, attempt in enumerate(attempts, start=1):
        user = db.query(UserProfile).filter_by(id=attempt.user_id).first()
        answers = db.query(RaceAnswer).filter_by(attempt_id=attempt.id).order_by(RaceAnswer.question_index).all()
        rows.append({"rank": rank, "display_name": attempt.display_name, "email": user.email if user else None, "score": attempt.score, "total_time_ms": attempt.total_time_ms, "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None, "answers": [{"question_index": answer.question_index, "selected_index": answer.selected_index, "is_correct": bool(answer.is_correct), "elapsed_ms": answer.elapsed_ms} for answer in answers]})
    return {"contest_date": day, "theme": quiz.theme if quiz else None, "questions": __import__('json').loads(quiz.questions_json) if quiz else [], "top_three": rows[:3], "attempts": rows}
@router.get("/admin/winners")
def admin_winners(db: Session = Depends(get_db), token=Depends(get_current_user_from_header)):
    require_admin(token); winners=db.query(RaceWinner).order_by(RaceWinner.contest_date.desc()).all(); return [{"contest_date": w.contest_date, "attempt_id": w.attempt_id, "name": db.query(UserProfile).filter_by(id=w.user_id).first().name, "email": db.query(UserProfile).filter_by(id=w.user_id).first().email} for w in winners]