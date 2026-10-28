"""Seed 20 persistent local AI Race test accounts. It never deletes data."""
from datetime import timedelta
import json
import os
from dotenv import load_dotenv
load_dotenv()

# Production safety guard: ONLY allow local databases, and only when ALLOW_SEED=1 is set.
db_url = os.getenv('DATABASE_URL', '')
allow_seed = os.getenv('ALLOW_SEED', '').strip() == '1'
is_local = (
    db_url.startswith('sqlite://') or
    'localhost' in db_url.lower() or
    '127.0.0.1' in db_url.lower()
)
if not (is_local and allow_seed):
    raise SystemExit("ERROR: This script must not run against a production database. "
                     "Set DATABASE_URL to a local database (sqlite://, localhost, or 127.0.0.1) "
                     "and set ALLOW_SEED=1 before running.")

from database import SessionLocal, init_db
from models.models import UserProfile, RaceDailyQuiz, RaceAttempt, RaceAnswer
from services.race_service import contest_date, now_ist

init_db()
db = SessionLocal()
day = contest_date()
if not db.query(RaceDailyQuiz).filter_by(contest_date=day).first():
    questions = [{"question": f"Test question {i + 1}", "options": ["A", "B", "C", "D"], "answer_index": 0} for i in range(15)]
    db.add(RaceDailyQuiz(contest_date=day, theme="Leaderboard verification", questions_json=json.dumps(questions), status="active"))

# Manoj 3 and Manoj 4 deliberately tie on score and total time; Manoj 3 finishes first.
results = [(15, 120000)] + [(14, 150000), (12, 180000), (12, 180000), (13, 160000), (11, 170000), (10, 180000), (9, 190000), (8, 200000), (7, 210000), (6, 220000), (5, 230000), (4, 240000), (3, 250000), (2, 260000), (15, 110000), (1, 270000), (0, 280000), (9, 195000), (10, 185000)]
# Index 15 is Manoj 16: intentional champion with fastest perfect score.
base = now_ist().replace(hour=10, minute=0, second=0, microsecond=0)
for number, (score, total_ms) in enumerate(results, start=1):
    email = f"manoj{number}@ai-race-test.local"
    user = db.query(UserProfile).filter_by(email=email).first()
    if not user:
        user = UserProfile(email=email, google_id=f"race-test-manoj-{number}", name=f"Manoj {number}", display_name=f"Manoj {number}")
        db.add(user); db.flush()
    else:
        user.display_name = f"Manoj {number}"
    attempt = db.query(RaceAttempt).filter_by(contest_date=day, user_id=user.id).first()
    if not attempt:
        # Existing real attempts are never overwritten; only create missing deterministic test attempts.
        finished_at = base + timedelta(minutes=number)
        attempt = RaceAttempt(contest_date=day, user_id=user.id, display_name=f"Manoj {number}", status="completed", current_question=15, score=score, total_time_ms=total_ms, question_started_at=base, completed_at=finished_at)
        db.add(attempt)
# Populate answer audit records only when a test attempt has none; nothing is deleted.
for attempt in db.query(RaceAttempt).filter_by(contest_date=day).all():
    if not db.query(RaceAnswer).filter_by(attempt_id=attempt.id).count():
        for question_index in range(15):
            is_correct = question_index < attempt.score
            db.add(RaceAnswer(attempt_id=attempt.id, question_index=question_index, selected_index=0 if is_correct else 1, is_correct=is_correct, elapsed_ms=max(1000, attempt.total_time_ms // 15)))
db.commit()
print(f"Seeded / retained 20 test users for {day}. No existing records were deleted.")
db.close()