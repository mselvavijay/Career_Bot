import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from database import engine, Base, init_db
from routers import career, auth, race

import time
from collections import defaultdict
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Initialize tables and apply schema migrations safely
try:
    init_db()
except Exception as e:
    print(f"Database initialization notice: {e}")

app = FastAPI(title="CareerBot AI - Executive Talent & Career Intelligence")

# 1. CORS Middleware - restrict to production domain and local development
ALLOWED_ORIGINS = [
    "https://hirekrkedekho.vercel.app",
    "https://hirekrkedekho.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 2. IP-based Rate Limiter (Token bucket per minute)
# 60 req/min for general API, 20 req/min for heavy AI / chat endpoints
RATE_LIMIT_STORE = defaultdict(list)
RATE_LIMITS = {
    "/chat": 20,
    "/auth/google": 15,
    "/race/start": 15,
    "/race/answer": 60,
}

@app.middleware("http")
async def security_and_ratelimit_middleware(request: Request, call_next):
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    path = request.url.path

    # Apply rate limiting to sensitive routes
    limit = RATE_LIMITS.get(path)
    if limit:
        now = time.time()
        window_start = now - 60
        # Clean timestamps older than 60 seconds
        RATE_LIMIT_STORE[client_ip] = [t for t in RATE_LIMIT_STORE[client_ip] if t > window_start]
        if len(RATE_LIMIT_STORE[client_ip]) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and try again shortly."}
            )
        RATE_LIMIT_STORE[client_ip].append(now)

    response = await call_next(request)

    # 3. Security Headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if path.startswith("/race/admin"):
        response.headers["Cache-Control"] = "no-store"
    return response

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML_PATH = TEMPLATES_DIR / "index.html"

if STATIC_DIR.exists():
    try:
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    except Exception:
        pass

app.include_router(auth.router)
app.include_router(career.router)
app.include_router(race.router)

@app.get("/", response_class=HTMLResponse)
def home():
    if INDEX_HTML_PATH.exists():
        return HTMLResponse(content=INDEX_HTML_PATH.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(content="<h1>CareerBot is operational</h1>", status_code=200)


@app.get("/race/admin", response_class=HTMLResponse)
def race_admin():
    path = TEMPLATES_DIR / "race_admin.html"
    return HTMLResponse(content=path.read_text(encoding="utf-8"), status_code=200)

@app.get("/consultation", response_class=HTMLResponse)
def consultation():
    if INDEX_HTML_PATH.exists():
        return HTMLResponse(content=INDEX_HTML_PATH.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(content="<h1>CareerBot consultation is unavailable</h1>", status_code=404)
@app.on_event("startup")
async def start_periodic_retention_scheduler():
    """Periodic retention cleanup scheduler running in background every 12 hours."""
    import asyncio
    async def periodic_cleanup():
        while True:
            try:
                await asyncio.sleep(12 * 3600)  # Run every 12 hours
                from services.response_cache import cleanup_expired_conversations
                from database import SessionLocal
                db = SessionLocal()
                try:
                    cleanup_expired_conversations(db)
                    from services.race_service import cleanup_expired_race_data
                    cleanup_expired_race_data(db, retention_days=7)
                finally:
                    db.close()
            except Exception as exc:
                print(f"Background retention scheduler notice: {exc}")
    asyncio.create_task(periodic_cleanup())

@app.get("/health")
def health():
    return {"status": "ok"}
