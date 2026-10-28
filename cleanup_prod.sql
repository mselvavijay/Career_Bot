-- cleanup_prod.sql
-- Run this manually in the Supabase SQL Editor to remove AI Race test data from production.
-- DO NOT run this on a production database with real users unless you have verified the SELECT checks below.
-- Default behavior: ROLLBACK (no changes). To actually delete, change the final ROLLBACK to COMMIT.

-- ============================================================
-- STEP 1: SELECT checks (verify what will be deleted)
-- ============================================================

-- Test attempts to be deleted (by test email domain)
SELECT 'race_attempts (test)' AS check_table, COUNT(*) AS row_count
FROM race_attempts ra
JOIN user_profiles up ON up.id = ra.user_id
WHERE up.email LIKE 'manoj%@ai-race-test.local';

-- Test answers to be deleted (linked to test attempts)
SELECT 'race_answers (test)' AS check_table, COUNT(*) AS row_count
FROM race_answers ra
JOIN race_attempts att ON att.id = ra.attempt_id
JOIN user_profiles up ON up.id = att.user_id
WHERE up.email LIKE 'manoj%@ai-race-test.local';

-- Test winners to be deleted
SELECT 'race_winners (test)' AS check_table, COUNT(*) AS row_count
FROM race_winners rw
JOIN race_attempts att ON att.id = rw.attempt_id
JOIN user_profiles up ON up.id = att.user_id
WHERE up.email LIKE 'manoj%@ai-race-test.local';

-- Test user_profiles to be deleted
SELECT 'user_profiles (test)' AS check_table, COUNT(*) AS row_count
FROM user_profiles
WHERE email LIKE 'manoj%@ai-race-test.local';

-- Test quiz row(s) with theme 'Leaderboard verification'
SELECT 'race_daily_quizzes (test theme)' AS check_table, COUNT(*) AS row_count
FROM race_daily_quizzes
WHERE theme = 'Leaderboard verification';

-- Check if any real (non-test) user has an attempt on the test quiz date(s)
-- This guards the quiz deletion: only delete the quiz if no real user attempted it.
SELECT 'real_users_on_test_quiz_dates' AS guard_check, COUNT(*) AS row_count
FROM race_attempts ra
JOIN user_profiles up ON up.id = ra.user_id
JOIN race_daily_quizzes q ON q.contest_date = ra.contest_date
WHERE q.theme = 'Leaderboard verification'
  AND up.email NOT LIKE 'manoj%@ai-race-test.local';

-- ============================================================
-- STEP 2: Deletion transaction (ROLLBACK by default)
-- ============================================================

BEGIN;

-- 1. Delete race_winners for test attempts first (FK dependency)
DELETE FROM race_winners
WHERE attempt_id IN (
    SELECT att.id FROM race_attempts att
    JOIN user_profiles up ON up.id = att.user_id
    WHERE up.email LIKE 'manoj%@ai-race-test.local'
);

-- 2. Delete race_answers for test attempts
DELETE FROM race_answers
WHERE attempt_id IN (
    SELECT att.id FROM race_attempts att
    JOIN user_profiles up ON up.id = att.user_id
    WHERE up.email LIKE 'manoj%@ai-race-test.local'
);

-- 3. Delete race_attempts for test users
DELETE FROM race_attempts
WHERE user_id IN (
    SELECT id FROM user_profiles
    WHERE email LIKE 'manoj%@ai-race-test.local'
);

-- 4. Delete test user_profiles
DELETE FROM user_profiles
WHERE email LIKE 'manoj%@ai-race-test.local';

-- 5. Delete the test quiz row only if no real user has an attempt on it
DELETE FROM race_daily_quizzes
WHERE theme = 'Leaderboard verification'
  AND NOT EXISTS (
    SELECT 1 FROM race_attempts ra
    JOIN user_profiles up ON up.id = ra.user_id
    WHERE ra.contest_date = race_daily_quizzes.contest_date
      AND up.email NOT LIKE 'manoj%@ai-race-test.local'
  );

-- Default: roll back so nothing is actually deleted.
-- To apply, change ROLLBACK to COMMIT and run again.
ROLLBACK;

-- COMMIT;