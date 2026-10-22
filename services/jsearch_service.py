import os
import httpx
import asyncio
from typing import Any
from dotenv import load_dotenv

load_dotenv()

JSEARCH_KEY = os.getenv("JSEARCH_API_KEY")
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"


async def get_jobs_from_jsearch(job_title: str, location: str = "India") -> list[str]:
    """
    Async version of the JSearch call.
    Called concurrently for multiple job titles using asyncio.gather in the router.
    """
    if not JSEARCH_KEY:
        return []

    headers = {
        "X-RapidAPI-Key": JSEARCH_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {
        "query": job_title,
        "num_pages": "1",
        "location": location,
        "country": "IN",
        "language": "en"
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(JSEARCH_URL, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        jobs = []
        if "data" in data and len(data["data"]) > 0:
            for job in data["data"][:5]:
                jobs.append(f"{job['job_title']} at {job['employer_name']} ({job['job_city']})")
        return jobs

    except Exception:
        # Silent fallback to LLM generated titles if API is down, rate-limited, or 404
        return []

async def get_recent_jobs_from_jsearch(job_titles: list[str], location: str = "India") -> list[dict[str, Any]]:
    """Return only India-based hybrid or remote roles posted in the last seven days."""
    if not JSEARCH_KEY or not job_titles:
        return []

    headers = {"X-RapidAPI-Key": JSEARCH_KEY, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}

    async def search(title: str) -> list[dict[str, Any]]:
        params = {"query": title, "location": location, "country": "IN", "date_posted": "week", "num_pages": "1"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(JSEARCH_URL, headers=headers, params=params)
                response.raise_for_status()
                data = response.json().get("data", [])
        except Exception:
            return []

        results = []
        for job in data:
            is_remote = bool(job.get("job_is_remote"))
            title_text = str(job.get("job_title") or "").strip()
            description = str(job.get("job_description") or "")
            hybrid = "hybrid" in f"{title_text} {description}".lower()
            if not title_text or not (is_remote or hybrid):
                continue
            mode = "Remote" if is_remote else "Hybrid"
            results.append({
                "title": title_text,
                "location": "India",
                "job_type": mode,
                "skills_required": [],
                "description": "Posted within the past week; review the live listing on LinkedIn.",
                "apply_url": job.get("job_apply_link") or f"https://www.linkedin.com/jobs/search/?keywords={title_text.replace(' ', '+')}&location=India"
            })
        return results

    batches = await asyncio.gather(*(search(title) for title in job_titles[:4]))
    unique = []
    seen = set()
    for job in (item for batch in batches for item in batch):
        key = job["title"].lower()
        if key not in seen:
            unique.append(job)
            seen.add(key)
        if len(unique) == 10:
            break
    return unique
