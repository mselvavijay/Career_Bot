# Production database checklist

## Vercel environment variables
Configure `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GROQ_API_KEY`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RACE_ENTRY_FEE_PAISE` for Production, Preview, and Development. Do not commit `.env` or any secret.

## Schema changes
Use Alembic for production schema changes:

```powershell
alembic upgrade head
alembic revision --autogenerate -m "describe schema change"
```

The app uses SQLAlchemy `NullPool` on Vercel so Supabase Shared Pooler connections are returned after each serverless request.
## LLM response cache

The app caches only standalone, non-time-sensitive career responses for 7 days. Cache keys include the normalized question, candidate profile fields, model name, and prompt version. Profile edits produce a new cache key automatically; consultation history remains separate and is never deleted by cache expiry.