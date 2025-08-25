from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import requests
from dotenv import load_dotenv

# ------------------ Load environment ------------------ #
load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY")
JSEARCH_KEY = os.getenv("JSEARCH_API_KEY")

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# ------------------ SYSTEM PROMPTS ------------------ #
system_extract = "You are an assistant that extracts main interests from user conversations. Answer in 1-2 short phrases separated by commas."
system_map = "You are a helpful assistant that maps interests to career paths from: STEM, Arts, Sports. Answer with only the category."
system_explain = "You are a career guide. Give a concise 1-2 sentence explanation for the recommended career path."

# ------------------ Interest to job titles ------------------ #
interest_to_jobs = {
    "coding": ["Software Engineer", "Backend Developer", "Full Stack Developer", "Data Analyst"],
    "dashboards": ["Data Analyst", "BI Developer", "Dashboard Developer", "UI/UX Designer"],
    "programming": ["Software Engineer", "Mobile App Developer", "Data Engineer"],
    "painting": ["Graphic Designer", "Illustrator", "Animator", "Art Teacher"],
    "music": ["Music Teacher", "Composer", "Sound Designer", "Performer"],
    "football": ["Football Coach", "Sports Analyst", "Physical Trainer"],
    "fitness": ["Personal Trainer", "Fitness Coach", "Yoga Instructor"],
    "basketball": ["Basketball Coach", "Sports Analyst", "Athletic Trainer"]
}

# ------------------ Helper Functions ------------------ #
def call_mistral(system_msg, user_msg):
    data = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ]
    }
    response = requests.post(BASE_URL, headers=HEADERS, json=data)
    result = response.json()
    if "choices" in result:
        return result["choices"][0]["message"]["content"].strip()
    else:
        return "Error: No response from model."

def get_jobs_from_jsearch(job_title, location="India"):
    headers = {
        "X-RapidAPI-Key": JSEARCH_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {"query": job_title, "num_pages": "1", "location": location, "country":"IN","language":"en"}
    response = requests.get(JSEARCH_URL, headers=headers, params=params)
    data = response.json()
    jobs = []
    if "data" in data and len(data["data"])>0:
        for job in data["data"][:5]:
            jobs.append(f"{job['job_title']} at {job['employer_name']} ({job['job_city']})")
    return jobs

# ------------------ FastAPI Setup ------------------ #
app = FastAPI(title="Career Bot API")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

class CareerRequest(BaseModel):
    user_input: str

# ------------------ API Endpoint ------------------ #
@app.post("/career-bot")
def career_bot(request: CareerRequest):
    user_input = request.user_input

    interests_text = call_mistral(system_extract, user_input)
    interests_list = []
    for i in interests_text.split(","):
        i = i.lower().replace("interests:", "").strip()
        if "dashboard" in i:
            i = "dashboards"
        if "coding" in i or "programming" in i:
            i = "coding"
        if "fitness" in i or "exercise" in i:
            i = "fitness"
        interests_list.append(i)

    map_prompt = f"The following are the user interests: {', '.join(interests_list)}. Which category do they best fit into among STEM, Arts, Sports?"
    career_category = call_mistral(system_map, map_prompt)

    explain_prompt = f"Explain why {career_category.strip()} is a good fit for someone interested in {', '.join(interests_list)}."
    explanation = call_mistral(system_explain, explain_prompt)

    all_jobs = []
    for interest in interests_list:
        job_titles = interest_to_jobs.get(interest, [])
        for title in job_titles:
            all_jobs += get_jobs_from_jsearch(title)
    all_jobs = list(dict.fromkeys(all_jobs))

    return {
        "interests": interests_list,
        "career_category": career_category,
        "explanation": explanation,
        "job_recommendations": all_jobs or ["No jobs found right now. Try another query."]
    }

# ------------------ Web Page ------------------ #
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
