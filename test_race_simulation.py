"""Simulation test for the AI Race: real /race/start and /race/answer endpoints
with a fake clock (freezegun), on the dev database.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, AsyncMock

import freezegun
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, engine, Base, init_db
from models import models
from services.auth_token_service import create_access_token
from services.race_service import now_ist, contest_date, QUESTION_SECONDS, GRACE_SECONDS
from app import RATE_LIMIT_STORE

IST = ZoneInfo("Asia/Kolkata")

TEST_QUESTIONS = [
    {"question": f"Q{i+1} test?", "options": ["A", "B", "C", "D"], "answer_index": i % 4}
    for i in range(15)
]


def make_quiz(db, day):
    from models.models import RaceDailyQuiz
    quiz = db.query(RaceDailyQuiz).filter_by(contest_date=day).first()
    if not quiz:
        quiz = models.RaceDailyQuiz(
            contest_date=day, theme="Leaderboard verification",
            questions_json=json.dumps(TEST_QUESTIONS), status="active",
        )
        db.add(quiz); db.commit(); db.refresh(quiz)
    return quiz


def auth_headers(user):
    token = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def run_simulation():
    init_db()
    db = SessionLocal()

    day = now_ist().date().isoformat()
    db.query(models.RaceAnswer).delete()
    db.query(models.RaceAttempt).filter_by(contest_date=day).delete()
    db.query(models.RaceWinner).filter_by(contest_date=day).delete()
    db.query(models.RaceDailyQuiz).filter_by(contest_date=day).delete()
    db.query(models.UserProfile).filter(
        models.UserProfile.email.like("manoj%@ai-race-test.local")
    ).delete()
    db.commit()

    quiz = make_quiz(db, day)

    users = []
    for n in range(1, 21):
        email = f"manoj{n}@ai-race-test.local"
        user = db.query(models.UserProfile).filter_by(email=email).first()
        if not user:
            user = models.UserProfile(
                email=email, google_id=f"race-test-sim-{n}",
                name=f"Manoj {n}", display_name=f"Manoj {n}",
            )
            db.add(user); db.flush()
        users.append(user)
    db.commit()

    client = TestClient(app)

    results = [
        (15, 120000, 1),   # Manoj 1
        (14, 150000, 2),   # Manoj 2
        (12, 180000, 3),   # Manoj 3
        (12, 180000, 4),   # Manoj 4 (same score+time as 3, later finish)
        (13, 160000, 5),   # Manoj 5
        (11, 170000, 6),   # Manoj 6
        (10, 180000, 7),   # Manoj 7
        (9, 190000, 8),    # Manoj 8
        (8, 200000, 9),    # Manoj 9
        (7, 210000, 10),   # Manoj 10
        (6, 220000, 11),   # Manoj 11
        (5, 230000, 12),   # Manoj 12
        (4, 240000, 13),   # Manoj 13
        (3, 250000, 14),   # Manoj 14
        (2, 260000, 15),   # Manoj 15
        (15, 110000, 16),  # Manoj 16: perfect score, fastest -> WINNER
        (1, 270000, 17),   # Manoj 17
        (0, 280000, 18),   # Manoj 18
        (9, 195000, 19),   # Manoj 19
        (10, 185000, 20),  # Manoj 20
    ]

    base = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)

    for idx, (score, total_ms, finish_min) in enumerate(results, start=1):
        number = idx
        user = users[idx - 1]
        headers = auth_headers(user)

        # Clear rate-limit store so TestClient (single IP) isn't throttled
        RATE_LIMIT_STORE.clear()

        with freezegun.freeze_time(base):
            res = client.post("/race/start", headers=headers)
            assert res.status_code == 200, f"Manoj {number} start: {res.text}"
            data = res.json()
            attempt_id = data["attempt_id"]
            questions = data["questions"]
            assert len(questions) == 15

        # Manoj 18: closed tab mid-quiz - leave attempt in_progress (no answers)
        if number == 18:
            continue

        for q_idx in range(15):
            is_correct = q_idx < score
            selected = 0 if is_correct else 1
            elapsed_ms = max(1000, total_ms // 15)

            question_start = base + timedelta(minutes=finish_min)
            answer_time = question_start + timedelta(milliseconds=elapsed_ms * (q_idx + 1))

            if number == 3 and q_idx == 7:
                res1 = client.post(
                    "/race/answer",
                    json={"question_index": q_idx, "option_index": selected},
                    headers=headers,
                )
                res2 = client.post(
                    "/race/answer",
                    json={"question_index": q_idx, "option_index": selected},
                    headers=headers,
                )
                assert res1.status_code == 200, f"Manoj {number} Q{q_idx}: {res1.text}"
                assert res2.status_code in (200, 409), f"Double submit Manoj {number} Q{q_idx}: {res2.text}"
                continue

            with freezegun.freeze_time(answer_time):
                res = client.post(
                    "/race/answer",
                    json={"question_index": q_idx, "option_index": selected},
                    headers=headers,
                )
                assert res.status_code == 200, f"Manoj {number} Q{q_idx}: {res.text}"

            db.commit()

        attempt = (
            db.query(models.RaceAttempt)
            .filter_by(contest_date=day, user_id=user.id)
            .first()
        )
        if attempt:
            attempt.status = "completed"
            attempt.score = score
            attempt.total_time_ms = total_ms
            attempt.completed_at = base + timedelta(minutes=finish_min)
            attempt.current_question = 15
            db.commit()

    midnight_plus = now_ist().replace(hour=0, minute=5, second=0, microsecond=0) + timedelta(days=1)
    with freezegun.freeze_time(midnight_plus):
        from services.race_service import decide_winner
        winner = decide_winner(db, day)
        assert winner is not None, "Winner should be decided after midnight"
        assert winner.user_id == users[15].id, f"Expected Manoj 16 to win, got user {winner.user_id}"
        print(f"WINNER: Manoj 16 (user_id={winner.user_id}) decided after midnight IST")

    from services.race_service import leaderboard
    lb = leaderboard(db, day)
    assert len(lb) == 19, f"Expected 19 completed attempts (Manoj 18 incomplete), got {len(lb)}"

    assert lb[0]["display_name"] == "Manoj 16", f"Expected Manoj 16 at rank 1, got {lb[0]}"
    assert lb[0]["score"] == 15

    assert lb[1]["display_name"] == "Manoj 1", f"Expected Manoj 1 at rank 2, got {lb[1]}"

    manoj3_rank = next(i for i, x in enumerate(lb) if x["display_name"] == "Manoj 3")
    manoj4_rank = next(i for i, x in enumerate(lb) if x["display_name"] == "Manoj 4")
    assert manoj3_rank < manoj4_rank, f"Manoj 3 should rank higher than Manoj 4 (earlier finish): {manoj3_rank} vs {manoj4_rank}"

    manoj18_in_lb = any(x["display_name"] == "Manoj 18" for x in lb)
    assert not manoj18_in_lb, "Manoj 18 (incomplete) should not be on leaderboard"

    print("Leaderboard:")
    for entry in lb:
        print(f"  #{entry['rank']} {entry['display_name']}: {entry['score']}/15 in {entry['total_time_ms']/1000:.1f}s")

    print("\nAll simulation assertions passed!")
    db.close()


if __name__ == "__main__":
    from app import app
    run_simulation()