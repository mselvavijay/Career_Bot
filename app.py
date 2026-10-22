import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from database import engine, Base
from routers import career

# Initialize tables safely
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Database initialization notice: {e}")

app = FastAPI(title="Career Bot API")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML_PATH = TEMPLATES_DIR / "index.html"

# Pre-cache index.html string for ultra-fast serverless delivery without jinja filesystem resolution errors
INDEX_HTML_CONTENT = ""
if INDEX_HTML_PATH.exists():
    try:
        INDEX_HTML_CONTENT = INDEX_HTML_PATH.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading index.html: {e}")

if STATIC_DIR.exists():
    try:
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    except Exception:
        pass

app.include_router(career.router)

@app.get("/", response_class=HTMLResponse)
def home():
    if INDEX_HTML_CONTENT:
        return HTMLResponse(content=INDEX_HTML_CONTENT, status_code=200)
    # Fallback to direct file read if not cached
    if INDEX_HTML_PATH.exists():
        return HTMLResponse(content=INDEX_HTML_PATH.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(content="<h1>Career Bot is running</h1>", status_code=200)

@app.get("/health")
def health():
    return {"status": "ok"}
