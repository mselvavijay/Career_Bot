import os
import httpx
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
