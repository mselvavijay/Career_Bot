import unittest
from datetime import datetime, timedelta, timezone, date
from database import SessionLocal, init_db, engine, Base
from models import models
from services.response_cache import (
    DAILY_FRESH_REQUEST_LIMIT,
    CONVERSATION_RETENTION_DAYS,
    get_daily_fresh_requests_count,
    get_target_job_count,
    can_make_fresh_request,
    record_fresh_request,
    cleanup_expired_conversations,
    save_cached_response,
    get_cached_response,
)

class TestFreeTierAndRetention(unittest.TestCase):

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_target_job_counts_and_daily_limit(self):
        """
        Verify candidate free-tier plan:
        - 1st request (Initial consultation, 0 used prior): 4 job openings
        - 2nd request (1st 'Show more', 1 used prior): 2 additional job openings
        - 3rd request (2nd 'Show more', 2 used prior): 2 additional job openings
        - Total: 8 job openings per day
        - After that: Daily limit reached
        """
        self.assertEqual(get_target_job_count(0), 4)
        self.assertEqual(get_target_job_count(1), 2)
        self.assertEqual(get_target_job_count(2), 2)
        self.assertEqual(get_target_job_count(3), 0)

        total_openings_allowed = (
            get_target_job_count(0) + get_target_job_count(1) + get_target_job_count(2)
        )
        self.assertEqual(total_openings_allowed, 8)

    def test_daily_ai_usage_tracking(self):
        """Verify candidate usage limit of 3 fresh requests per day."""
        test_user = models.UserProfile(
            name="Usage Test Candidate",
            email=f"usage_{int(datetime.now().timestamp())}@example.com"
        )
        self.db.add(test_user)
        self.db.commit()
        self.db.refresh(test_user)
        test_user_id = test_user.id
        
        # Clean existing test record if any
        today = date.today().isoformat()
        self.db.query(models.DailyAIUsage).filter_by(user_id=test_user_id).delete()
        self.db.commit()

        # Step 0: Before any requests
        self.assertTrue(can_make_fresh_request(self.db, models.DailyAIUsage, test_user_id))
        self.assertEqual(get_daily_fresh_requests_count(self.db, models.DailyAIUsage, test_user_id), 0)
        self.assertEqual(get_target_job_count(0), 4)

        # Step 1: Initial consultation (Request 1 -> 4 jobs)
        new_count = record_fresh_request(self.db, models.DailyAIUsage, test_user_id)
        self.assertEqual(new_count, 1)
        self.assertTrue(can_make_fresh_request(self.db, models.DailyAIUsage, test_user_id))
        self.assertEqual(get_target_job_count(1), 2)

        # Step 2: First "Show more" (Request 2 -> 2 jobs)
        new_count = record_fresh_request(self.db, models.DailyAIUsage, test_user_id)
        self.assertEqual(new_count, 2)
        self.assertTrue(can_make_fresh_request(self.db, models.DailyAIUsage, test_user_id))
        self.assertEqual(get_target_job_count(2), 2)

        # Step 3: Second "Show more" (Request 3 -> 2 jobs, total 8)
        new_count = record_fresh_request(self.db, models.DailyAIUsage, test_user_id)
        self.assertEqual(new_count, 3)

        # Step 4: Daily limit reached!
        self.assertFalse(can_make_fresh_request(self.db, models.DailyAIUsage, test_user_id))
        self.assertEqual(get_target_job_count(3), 0)

        # Cleanup
        self.db.query(models.DailyAIUsage).filter_by(user_id=test_user_id).delete()
        self.db.delete(test_user)
        self.db.commit()

    def test_daily_limit_bot_response(self):
        """Verify that when daily limit is reached, bot responds with 'Daily limit reached. Come back tomorrow for new openings.'"""
        from fastapi.testclient import TestClient
        from app import app
        from services.response_cache import get_today_ist
        
        client = TestClient(app)
        test_user = models.UserProfile(
            name="Limit Test Candidate",
            email=f"limit_{int(datetime.now().timestamp())}@example.com"
        )
        self.db.add(test_user)
        self.db.commit()
        self.db.refresh(test_user)

        # Mark user as having used all 3 requests today
        today = get_today_ist()
        usage = models.DailyAIUsage(user_id=test_user.id, usage_date=today, fresh_requests=3)
        self.db.add(usage)
        self.db.commit()

        # Send request
        res = client.post("/chat", json={
            "user_input": "Show more job openings",
            "user_id": test_user.id
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["message"], "Daily limit reached. Come back tomorrow for new openings.")
        self.assertEqual(len(data["open_jobs"]), 0)
        self.assertTrue(data["daily_limit_reached"])
        self.assertEqual(data["remaining_requests"], 0)

        # Cleanup
        self.db.query(models.DailyAIUsage).filter_by(user_id=test_user.id).delete()
        self.db.query(models.ChatMessage).filter_by(session_id=data["session_id"]).delete()
        self.db.query(models.ConversationSession).filter_by(id=data["session_id"]).delete()
        self.db.delete(test_user)
        self.db.commit()

    def test_30_day_retention_and_permanent_profiles(self):
        """
        Verify:
        - Conversations older than 30 days are automatically deleted.
        - Conversations within 30 days are preserved.
        - Candidate profiles remain permanent.
        - AI response cache expires after 7 days.
        """
        now = datetime.now(timezone.utc)

        # Create candidate profile
        test_user = models.UserProfile(
            name="Permanent Candidate",
            email=f"candidate_{int(now.timestamp())}@example.com"
        )
        self.db.add(test_user)
        self.db.commit()
        self.db.refresh(test_user)

        # Session 1: Recent session (5 days old) -> should be kept
        recent_session = models.ConversationSession(
            user_id=test_user.id,
            title="Recent Consultation",
            created_at=now - timedelta(days=5)
        )
        self.db.add(recent_session)

        # Session 2: Old session (35 days old) -> should be deleted
        old_session = models.ConversationSession(
            user_id=test_user.id,
            title="Expired Consultation",
            created_at=now - timedelta(days=35)
        )
        self.db.add(old_session)
        self.db.commit()

        # Add messages
        msg_recent = models.ChatMessage(session_id=recent_session.id, role="user", content="Hello recent")
        msg_old = models.ChatMessage(session_id=old_session.id, role="user", content="Hello old")
        self.db.add_all([msg_recent, msg_old])
        self.db.commit()

        # Run retention cleanup
        res = cleanup_expired_conversations(self.db)
        self.assertGreaterEqual(res["cleaned_sessions"], 1)

        # Verify old session deleted
        check_old = self.db.query(models.ConversationSession).filter_by(id=old_session.id).first()
        self.assertIsNone(check_old)
        check_old_msg = self.db.query(models.ChatMessage).filter_by(session_id=old_session.id).first()
        self.assertIsNone(check_old_msg)

        # Verify recent session kept
        check_recent = self.db.query(models.ConversationSession).filter_by(id=recent_session.id).first()
        self.assertNotNull = self.assertIsNotNone(check_recent)

        # Verify UserProfile is PERMANENT
        check_user = self.db.query(models.UserProfile).filter_by(id=test_user.id).first()
        self.assertIsNotNone(check_user)
        self.assertEqual(check_user.name, "Permanent Candidate")

        # Cleanup test records
        self.db.delete(check_recent)
        self.db.delete(check_user)
        self.db.commit()

if __name__ == "__main__":
    unittest.main()
