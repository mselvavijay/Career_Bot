import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from database import engine, Base, init_db
from routers import career, auth

# Initialize tables and apply schema migrations safely
try:
    init_db()
except Exception as e:
    print(f"Database initialization notice: {e}")

app = FastAPI(title="CareerBot AI - Executive Talent & Career Intelligence")

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

@app.get("/", response_class=HTMLResponse)
def home():
    if INDEX_HTML_PATH.exists():
        return HTMLResponse(content=INDEX_HTML_PATH.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(content="<h1>CareerBot is operational</h1>", status_code=200)

@app.get("/health")
def health():
    return {"status": "ok"}
