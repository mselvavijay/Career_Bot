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
INDEED_KEY = os.getenv("INDEED_API_KEY")
INDEED_HOST = os.getenv("INDEED_API_HOST", "indeed11.p.rapidapi.com")
INDEED_URL = os.getenv("INDEED_API_URL", "https://indeed11.p.rapidapi.com/")

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# ------------------ SYSTEM PROMPTS ------------------ #
system_extract = "You are an assistant that extracts main interests from user conversations. Answer in 1-2 short phrases separated by commas."
system_map = "You are a helpful assistant that maps interests to career paths from: STEM, Arts, Sports. Answer with only the category."
system_explain = "You are a career guide. Give a concise 1-2 sentence explanation for the recommended career path."

# ------------------ Interest to job titles ------------------ #
interest_map = {
    "dashboard": "dashboards",
    "dashboards": "dashboards",
    "coding": "coding",
    "programming": "coding",
    "fitness": "fitness",
    "exercise": "fitness",
    "painting": "painting",
    "music": "music",
    "football": "football",
    "basketball": "basketball",
    "web designing": "web_design",
    "web design": "web_design"
}

interest_to_jobs = {
    "coding": ["Software Engineer", "Backend Developer", "Full Stack Developer", "Data Analyst"],
    "dashboards": ["Data Analyst", "BI Developer", "Dashboard Developer", "UI/UX Designer"],
    "painting": ["Graphic Designer", "Illustrator", "Animator", "Art Teacher"],
    "music": ["Music Teacher", "Composer", "Sound Designer", "Performer"],
    "football": ["Football Coach", "Sports Analyst", "Physical Trainer"],
    "fitness": ["Personal Trainer", "Fitness Coach", "Yoga Instructor"],
    "basketball": ["Basketball Coach", "Sports Analyst", "Athletic Trainer"],
    "web_design": ["Web Designer", "Front-End Developer", "UI/UX Designer"]
}

# ------------------ Helper Functions ------------------ #
def call_mistral(system_msg, user_msg):
    try:
        data = {
            "model": "mistralai/mistral-7b-instruct",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ]
        }
        response = requests.post(BASE_URL, headers=HEADERS, json=data, timeout=30)
        result = response.json()
        if "choices" in result:
            return result["choices"][0]["message"]["content"].strip()
        else:
            return "Error: No response from model."
    except Exception as e:
        print("Error calling Mistral:", e)
        return "Error: Could not call model."


def get_jobs_from_indeed(job_title, location="India"):
    try:
        headers = {
            "X-RapidAPI-Key": INDEED_KEY,
            "X-RapidAPI-Host": INDEED_HOST
        }
        params = {
            "query": job_title,
            "location": location,
            "page": "1"
        }

        url = INDEED_URL + "jobs/search"
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()

        jobs = []
        # Adjusting parsing for Indeed API response
        if "results" in data and len(data["results"]) > 0:
            for job in data["results"][:5]:
                title = job.get("title", "Unknown Title")
                company = job.get("company", "Unknown Company")
                city = job.get("location", "Unknown Location")
                jobs.append(f"{title} at {company} ({city})")

        return jobs
    except Exception as e:
        print("Error calling Indeed API:", e)
        return []

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

    # Step 1: Extract interests using Mistral
    interests_text = call_mistral(system_extract, user_input)
    interests_list = []

    for i in interests_text.split(","):
        i = i.lower().replace("interests:", "").strip()
        i = interest_map.get(i, i)  # normalize using mapping
        interests_list.append(i)

    print("Extracted interests:", interests_text)
    print("Normalized interests:", interests_list)

    # Step 2: Map to career category
    map_prompt = f"The following are the user interests: {', '.join(interests_list)}. Which category do they best fit into among STEM, Arts, Sports?"
    career_category = call_mistral(system_map, map_prompt)

    # Step 3: Explain career choice
    explain_prompt = f"Explain why {career_category.strip()} is a good fit for someone interested in {', '.join(interests_list)}."
    explanation = call_mistral(system_explain, explain_prompt)

    # Step 4: Get job recommendations
    all_jobs = []
    for interest in interests_list:
        job_titles = interest_to_jobs.get(interest, [])
        for title in job_titles:
            jobs = get_jobs_from_indeed(title)
            if jobs:
                all_jobs += jobs

    # Remove duplicates
    all_jobs = list(dict.fromkeys(all_jobs))

    if not all_jobs:
        all_jobs = ["No jobs found right now. Try another query."]

    return {
        "interests": interests_list,
        "career_category": career_category,
        "explanation": explanation,
        "job_recommendations": all_jobs
    }

# ------------------ Web Page ------------------ #
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
