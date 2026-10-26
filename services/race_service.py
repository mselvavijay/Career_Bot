import json
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.models import RaceDailyQuiz, RaceAttempt, RaceAnswer, RaceWinner

IST = timezone(timedelta(hours=5, minutes=30))
QUESTION_SECONDS = 15
GRACE_SECONDS = 2
QUESTION_COUNT = 15
THEMES = ("Python fundamentals", "SQL", "JavaScript", "Data structures", "Git and Linux")


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


async def _groq_json(messages: list[dict[str, str]]) -> Any:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return []
    payload = {"model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), "messages": messages, "temperature": 0.2, "response_format": {"type": "json_object"}}
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload)
        response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


async def create_daily_quiz(db: Session, day: str) -> RaceDailyQuiz:
    existing = db.query(RaceDailyQuiz).filter_by(contest_date=day).first()
    if existing:
        return existing
    theme = today_theme(day)
    prompt = f'''Create 20 easy multiple-choice quiz questions on {theme} for a daily tech contest. Return JSON {{"questions":[{{"question":"...","options":["...","...","...","..."],"answer_index":0}}]}}. Exactly four options, one answer, no ambiguous questions.'''
    try:
        generated = (await _groq_json([{"role": "user", "content": prompt}])).get("questions", [])
        verifier_prompt = "Solve these questions independently. Return JSON {\"answers\":[0,...]}; one zero-based answer index per question only.\n" + json.dumps(generated)
        verified = (await _groq_json([{"role": "user", "content": verifier_prompt}])).get("answers", [])
        questions = [q for i, q in enumerate(generated) if isinstance(q, dict) and len(q.get("options", [])) == 4 and q.get("answer_index") == (verified[i] if i < len(verified) else None)][:QUESTION_COUNT]
    except Exception:
        questions = []
    if len(questions) < QUESTION_COUNT:
        # Safe local fallback keeps the contest available if Groq is unavailable.
        questions = [{"question": f"Which option is the correct answer for {theme} practice question {i + 1}?", "options": ["Option A", "Option B", "Option C", "Option D"], "answer_index": i % 4} for i in range(QUESTION_COUNT)]
    quiz = RaceDailyQuiz(contest_date=day, theme=theme, questions_json=json.dumps(questions), status="active")
    db.add(quiz); db.commit(); db.refresh(quiz)
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