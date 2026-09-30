from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import models
from schemas import schemas
from services.llm_service import call_mistral
from services.jsearch_service import get_jobs_from_jsearch

router = APIRouter()

system_extract = "You are an assistant that extracts main interests from user conversations. Answer in 1-2 short phrases separated by commas."
system_map = "You are a helpful assistant that maps interests to career paths from: STEM, Arts, Sports. Answer with only the category."
system_explain = "You are a career guide. Give a concise 1-2 sentence explanation for the recommended career path."
system_job_titles = "You are a career assistant. Generate 5-10 relevant job titles for a person interested in these topics."

@router.post("/career-bot", response_model=schemas.CareerResponse)
def career_bot(request: schemas.CareerRequest, db: Session = Depends(get_db)):
    user_input = request.user_input
    
    # 1. Extract interests
    interests_text = call_mistral(system_extract, user_input)
    interests_list = [i.strip().lower() for i in interests_text.split(",") if i.strip()]
    
    # 2. Map to category
    map_prompt = f"The following are the user interests: {', '.join(interests_list)}. Which category do they best fit into among STEM, Arts, Sports?"
    career_category = call_mistral(system_map, map_prompt)
    
    # 3. Explain
    explain_prompt = f"Explain why {career_category.strip()} is a good fit for someone interested in {', '.join(interests_list)}."
    explanation = call_mistral(system_explain, explain_prompt)
    
    # 4. Generate Job Titles (LLM) and Fetch Real Jobs (JSearch)
    job_titles_prompt = f"Suggest 5-10 realistic job titles for someone interested in {', '.join(interests_list)}."
    job_titles_text = call_mistral(system_job_titles, job_titles_prompt)
    llm_job_titles = [jt.strip() for jt in job_titles_text.split("\n") if jt.strip()]
    
    final_jobs = []
    # Try fetching real jobs for a couple of top LLM suggestions
    for title in llm_job_titles[:3]: 
        # Clean title (e.g. remove numbering "1. Software Engineer")
        clean_title = title.split(".", 1)[-1].strip() if "." in title[:3] else title
        real_jobs = get_jobs_from_jsearch(clean_title)
        final_jobs.extend(real_jobs)
    
    # Deduplicate
    final_jobs = list(dict.fromkeys(final_jobs))
    
    # If no real jobs found, fallback to LLM suggestions
    if not final_jobs:
        final_jobs = llm_job_titles
        
    # Save to database
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
