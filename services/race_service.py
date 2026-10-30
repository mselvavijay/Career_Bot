import json
import os
import re
import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.models import RaceDailyQuiz, RaceAttempt, RaceAnswer, RaceWinner, RaceQuestionArchive
# ── In-process cache for today's quiz (avoids DB round-trip on each answer) ──
_quiz_cache: dict = {}


def get_cached_quiz(db, day: str):
    """Return today's quiz from process cache; fall back to DB and cache it."""
    global _quiz_cache
    if day in _quiz_cache:
        return _quiz_cache[day]
    quiz = db.query(RaceDailyQuiz).filter_by(contest_date=day).first()
    if quiz:
        _quiz_cache = {day: quiz}   # evict stale dates automatically
    return quiz



IST = timezone(timedelta(hours=5, minutes=30))
QUESTION_SECONDS = 15
GRACE_SECONDS = 2
QUESTION_COUNT = 15
THEMES = ("Python fundamentals", "SQL", "JavaScript", "Data structures", "Git and Linux")

# Question-quality windows
AVOID_DAYS = 7
HASH_WINDOW_DAYS = 30


def now_ist() -> datetime:
    return datetime.now(IST)


def contest_date() -> str:
    return now_ist().date().isoformat()


def today_theme(day: str) -> str:
    return THEMES[datetime.fromisoformat(day).toordinal() % len(THEMES)]


def public_name(value: str | None) -> str:
    value = re.sub(r"[^A-Za-z0-9 _-]", "", (value or "")).strip()
    if len(value) < 3 or value.replace(" ", "").isdigit():
        return "player"
    return value[:30]


def normalise_text(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def question_hash(text: str) -> str:
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


def _recent_question_hashes(db: Session, days: int) -> set[str]:
    cutoff = (now_ist() - timedelta(days=days)).date().isoformat()
    rows = db.query(RaceQuestionArchive).filter(RaceQuestionArchive.contest_date >= cutoff).all()
    return {r.question_hash for r in rows}


async def _groq_json(messages: list[dict[str, str]]) -> Any:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return []
    payload = {"model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), "messages": messages, "temperature": 0.2, "response_format": {"type": "json_object"}}
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload)
        response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


async def create_daily_quiz(db: Session, day: str) -> RaceDailyQuiz | None:
    existing = db.query(RaceDailyQuiz).filter_by(contest_date=day).first()
    if existing:
        return existing
    theme = today_theme(day)

    avoid_hashes = _recent_question_hashes(db, HASH_WINDOW_DAYS)

    try:
        prompt = f"""Create 20 easy multiple-choice quiz questions on {theme} for a daily tech contest. Return JSON {{\"questions\":[{{\"question\":\"...\",\"options\":[\"...\",\"...\",\"...\",\"...\"],\"answer_index\":0}}]}}. Exactly four options, one answer, no ambiguous questions."""
        generated = (await _groq_json([{"role": "user", "content": prompt}])).get("questions", [])
        verifier_prompt = 'Solve these questions independently. Return JSON {"answers":[0,...]}; one zero-based answer index per question only.\n' + json.dumps(generated)
        verified = (await _groq_json([{"role": "user", "content": verifier_prompt}])).get("answers", [])

        questions = []
        for i, q in enumerate(generated):
            if not isinstance(q, dict):
                continue
            if len(q.get("options", [])) != 4:
                continue
            if q.get("answer_index") != (verified[i] if i < len(verified) else None):
                continue
            q_text = q.get("question", "")
            q_h = question_hash(q_text)
            if q_h in avoid_hashes:
                continue
            questions.append(q)
            if len(questions) >= QUESTION_COUNT:
                break
    except Exception:
        questions = []

    if len(questions) < QUESTION_COUNT:
        return None

    quiz = RaceDailyQuiz(contest_date=day, theme=theme, questions_json=json.dumps(questions), status="active")
    db.add(quiz); db.commit(); db.refresh(quiz)

    for q in questions:
        q_h = question_hash(q.get("question", ""))
        db.add(RaceQuestionArchive(contest_date=day, question_hash=q_h))
    db.commit()

    return quiz




def questions_for_player(quiz: RaceDailyQuiz) -> list[dict[str, Any]]:
    return [{"index": i, "question": q["question"], "options": q["options"]} for i, q in enumerate(json.loads(quiz.questions_json))]


def leaderboard(db: Session, day: str) -> list[dict[str, Any]]:
    rows = db.query(RaceAttempt).filter_by(contest_date=day, status="completed").order_by(RaceAttempt.score.desc(), RaceAttempt.total_time_ms.asc(), RaceAttempt.completed_at.asc()).all()
    return [{"rank": i + 1, "display_name": a.display_name, "score": a.score, "total_time_ms": a.total_time_ms} for i, a in enumerate(rows)]


def decide_winner(db: Session, day: str) -> RaceWinner | None:
    if now_ist().date().isoformat() <= day:
        return None
    winner = db.query(RaceWinner).filter_by(contest_date=day).first()
    if winner:
        return winner
    attempt = db.query(RaceAttempt).filter_by(contest_date=day, status="completed").order_by(RaceAttempt.score.desc(), RaceAttempt.total_time_ms.asc(), RaceAttempt.completed_at.asc()).first()
    if not attempt:
        return None
    winner = RaceWinner(contest_date=day, attempt_id=attempt.id, user_id=attempt.user_id)
    db.add(winner); db.commit(); return winner


def cleanup_expired_race_data(db: Session, retention_days: int = 7) -> dict[str, int]:
    """Deletes all contest data older than retention_days (default 7 days).
    Deletes in FK-safe order: winners -> answers -> attempts -> daily quizzes.
    Does NOT delete user_profiles (users remain intact).
    """
    cutoff_date = (now_ist() - timedelta(days=retention_days)).date().isoformat()
    old_attempts = db.query(RaceAttempt).filter(RaceAttempt.contest_date < cutoff_date).all()
    old_attempt_ids = [a.id for a in old_attempts]

    deleted_counts = {"winners": 0, "answers": 0, "attempts": 0, "quizzes": 0, "archives": 0}

    if old_attempt_ids:
        deleted_counts["winners"] = db.query(RaceWinner).filter(
            (RaceWinner.contest_date < cutoff_date) | (RaceWinner.attempt_id.in_(old_attempt_ids))
        ).delete(synchronize_session=False)

        deleted_counts["answers"] = db.query(RaceAnswer).filter(
            RaceAnswer.attempt_id.in_(old_attempt_ids)
        ).delete(synchronize_session=False)

        deleted_counts["attempts"] = db.query(RaceAttempt).filter(
            RaceAttempt.id.in_(old_attempt_ids)
        ).delete(synchronize_session=False)
    else:
        deleted_counts["winners"] = db.query(RaceWinner).filter(
            RaceWinner.contest_date < cutoff_date
        ).delete(synchronize_session=False)

    deleted_counts["quizzes"] = db.query(RaceDailyQuiz).filter(
        RaceDailyQuiz.contest_date < cutoff_date
    ).delete(synchronize_session=False)

    deleted_counts["archives"] = db.query(RaceQuestionArchive).filter(
        RaceQuestionArchive.contest_date < cutoff_date
    ).delete(synchronize_session=False)

    db.commit()
    return deleted_counts
