import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import models
from schemas import schemas
from services.llm_service import analyze_user_input
from services.jsearch_service import get_jobs_from_jsearch

router = APIRouter()


@router.post("/career-bot", response_model=schemas.CareerResponse)
async def career_bot(request: schemas.CareerRequest, db: Session = Depends(get_db)):
    user_input = request.user_input

    # STEP 1: Single LLM call — replaces 4 sequential calls
    # Returns interests, career_category, explanation, and job_titles all at once
    llm_result = await analyze_user_input(user_input)

    interests_list = llm_result.get("interests", [])
    career_category = llm_result.get("career_category", "STEM")
    explanation = llm_result.get("explanation", "")
    llm_job_titles = llm_result.get("job_titles", [])

    # STEP 2: Fetch real jobs from JSearch — all 3 searches run IN PARALLEL
    # Instead of waiting for each one to finish, we fire all 3 at the same time
    top_titles = [
        title.split(".", 1)[-1].strip() if "." in title[:3] else title
        for title in llm_job_titles[:3]
    ]

    job_results = await asyncio.gather(
        *[get_jobs_from_jsearch(title) for title in top_titles],
        return_exceptions=True  # Don't crash if one JSearch call fails
    )

    # Flatten results and filter out any failed (exception) responses
    final_jobs = []
    for result in job_results:
        if isinstance(result, list):
            final_jobs.extend(result)

    # Deduplicate
    final_jobs = list(dict.fromkeys(final_jobs))

    # If no real jobs found, fallback to LLM suggestions
    if not final_jobs:
        final_jobs = llm_job_titles

    # STEP 3: Save to database
    db_history = models.ChatHistory(
        user_input=user_input,
        extracted_interests=",".join(interests_list),
        career_category=career_category,
        explanation=explanation,
        job_titles=",".join(final_jobs)
    )
    db.add(db_history)
    db.commit()
    db.refresh(db_history)

    return schemas.CareerResponse(
        interests=interests_list,
        career_category=career_category,
        explanation=explanation,
        job_titles=final_jobs
    )
