# Project Architecture Update: Layman's Guide

This document explains what has been updated in the HireKrkeDekho / Career Bot project, step-by-step, and **why** those changes were made. The goal of these updates is to provide an **enterprise-grade, production-ready, cost-effective, and mobile-responsive AI talent advisory platform**.

---

## 1. Creating `requirements.txt` (The Grocery List)
**What we did:** We created a file that lists all external dependencies (`fastapi`, `uvicorn`, `sqlalchemy`, `httpx`, `psycopg2-binary`, `python-dotenv`).
**Why we did it:** Acting as the official recipe ingredient list, it ensures seamless installation on local machines, Vercel, Docker, and AWS without missing libraries.

---

## 2. Introducing a Database (Memory & Multi-Engine Compatibility)
**What we did:** Added `database.py` and `models/models.py`.
**Why we did it:** The bot needs to remember sessions, conversations, and candidate profiles.
- **Dual Support:** Uses SQLite locally for rapid development and seamlessly connects to managed PostgreSQL (Supabase) in production.
- **Connection Pooling:** Serverless-aware with `NullPool` so connection limits are never exhausted on cloud deployments.

---

## 3. Creating "Schemas" (The Bouncer & Formatter)
**What we did:** Added `schemas/schemas.py` using Pydantic.
**Why we did it:** Validates all incoming API payloads and ensures the frontend consistently receives strict, structured data (e.g. `JobListing`, `MultiTurnChatResponse`).

---

## 4. Organizing with "Services" (The Specialized Workers)
**What we did:** Separated business logic into dedicated service modules:
- `llm_service.py`: Handles Groq / OpenRouter API interaction and structured JSON output.
- `jsearch_service.py`: Real-time job retrieval with fallback.
- `guardrail_service.py`: Zero-cost rule-based input/output security and topic gating.
- `response_cache.py`: 7-day response cache, daily candidate usage tracking, and 30-day retention cleanup.

---

## 5. Setting up "Routers" (The Traffic Controllers)
**What we did:** Organized HTTP endpoints into dedicated routers:
- `routers/career.py`: Multi-turn chat, session history, profile management, and job recommendations.
- `routers/auth.py`: Google Identity OAuth and profile synchronization.
- `routers/race.py`: Daily contest status and Razorpay checkout orders.

---

## 6. Single Source of Truth for App Entry & Styling
**What we did:** Cleaned up `app.py` as a lightweight app orchestrator and **deleted redundant `style.css`**.
**Why we did it:** 
- `app.py` simply mounts routes, static files, and initializes tables.
- `style.css` was an obsolete 93-line file overridden by `app.css`. Consolidating into `static/app.css` eliminates duplicate styles and creates a single styling source of truth.

---

## 7. Speed Optimizations: Async & Parallel API Calls
**What we did:** Implemented async HTTP (`httpx`) and `asyncio.gather()`.
**Why we did it:** Reduced overall query latency by ~70% (from ~25 seconds down to ~4–7 seconds) by sending parallel requests instead of blocking sequential queries.

---

## 8. Multi-Turn Conversation Memory & Sessions
**What we did:** Created `ConversationSession` and `ChatMessage` models with `/sessions` endpoints.
**Why we did it:** Candidates can have persistent, threaded dialogues. The advisor remembers previous roles recommended and builds on earlier answers across turns.

---

## 9. Six-Layer Guardrails Pipeline ($0-Cost Safety & Topic Gating)
**What we did:** Added `services/guardrail_service.py` evaluated before any LLM call:
1. **Normalization:** Strips zero-width characters, spacing tricks, and leetspeak.
2. **Safety & Abuse Filter:** Rejects harmful, illegal, explicit, or malicious content instantly.
3. **Small-Talk & Greetings:** Fast friendly responses for "hi", "bye", or "thanks" at $0 cost without calling the LLM.
4. **Scope Gating:** Politely declines non-tech questions and steers back to tech careers.
5. **Prompt Injection Defense:** Neutralizes system prompt override attempts.
6. **Output Hallucination & PII Check:** Ensures assistant responses contain no inappropriate output or sensitive leaked keys.

---

## 10. Tri-Factor Grounding (Degree + Experience + Skills)
**What we did:** Grounded AI recommendations directly in the candidate's profile:
- **Degree:** Foundation and qualification requirements.
- **Experience:** Seniority level and calibrated Indian tech compensation (e.g. 0 yrs: 4–9 LPA, 1–3 yrs: 8–16 LPA, 4–7 yrs: 18–32 LPA, 8+ yrs: 35–60 LPA).
- **Core Skills:** Specific frameworks, languages, and technical competencies.
- **Prep Guide:** Each job listing includes a structured 3-Week Preparation Roadmap.

---

## 11. Free-Tier Daily Plan & Job Openings Calibration
**What we did:** Aligned job openings with candidate daily AI usage:
- **Initial Fresh Consultation:** **4 curated job openings**
- **First "Show More":** **2 additional openings**
- **Second "Show More":** **2 additional openings**
- **Total Quota:** **8 openings per candidate per day** across 3 fresh requests.
- **Daily Limit Behavior:**
  - After 3 requests, requests return: `"Daily limit reached. Come back tomorrow for new openings."`
  - The UI dynamically displays a clear daily limit banner and disables further quota consumption until the next day.

---

## 12. 30-Day Chat Retention & Supabase Space Recovery
**What we did:** Implemented automated 30-day data retention:
- **Conversations:** Sessions and messages older than 30 days are automatically purged via `cleanup_expired_conversations(db)`.
- **Space Recovery:** Prevents unlimited database growth and stays comfortably within Supabase free-tier limits.
- **AI Response Cache:** Cached standalone questions expire after 7 days (`CACHE_TTL = 7 days`).
- **Permanent Profiles:** Candidate user profiles (`user_profiles`) are **permanent** and never deleted.

---

## Summary of Current Architecture

| Component | Responsibility | Tech / Mechanism |
|---|---|---|
| **Frontend** | Dark mode UI, glassmorphism, responsive chat workspace | Vanilla HTML, CSS (`app.css`), JavaScript (`app.js`) |
| **API Server** | Async REST endpoints, routing, static hosting | FastAPI, Uvicorn |
| **Guardrails** | Instant zero-cost filtering, safety, topic gating | Regex, leetspeak decoder, in-memory cache |
| **Intelligence** | Structured JSON generation, career guidance | Groq / OpenRouter, `gpt-oss-120b` / `mistral-7b` |
| **Storage** | Relational data, candidate profiles, session history | PostgreSQL (Supabase) / SQLite via SQLAlchemy |
| **Cache & Quota** | 7-day LLM cache, daily 4/2/2 opening limit, 30-day retention | `DailyAIUsage`, `LLMResponseCache`, cascade deletion |
