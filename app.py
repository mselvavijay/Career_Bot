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

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# ------------------ SYSTEM PROMPTS ------------------ #
system_extract = "You are an assistant that extracts main interests from user conversations. Answer in 1-2 short phrases separated by commas."
system_map = "You are a helpful assistant that maps interests to career paths from: STEM, Arts, Sports. Answer with only the category."
system_explain = "You are a career guide. Give a concise 1-2 sentence explanation for the recommended career path."
system_job = """
You are a career guide that suggests 5-10 job titles suitable for the user interests in India.
Output ONLY the job titles, separated strictly by commas, with NO extra text.
"""

# ------------------ Interest normalization ------------------ #
interest_map = {
    "dashboard": "dashboards",
    "dashboards": "dashboards",
    "coding": "coding",
    "programming": "coding",
    "fitness": "fitness",
    "exercise": "fitness",
    "painting": "painting",
    "music": "music",
    "singing": "music",
    "composing music": "music",
    "football": "football",
    "basketball": "basketball",
    "web designing": "web_design",
    "web design": "web_design"
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

def generate_jobs_with_llm(interests_list):
    # Join interests and prompt LLM
    prompt = f"Suggest 5-10 job titles in India for someone interested in: {', '.join(interests_list)}."
    jobs_text = call_mistral(system_job, prompt)

    # Clean LLM output
    jobs_text = jobs_text.replace("\n", "").replace("-", "").replace(".", "")
    jobs = [j.strip() for j in jobs_text.split(",") if j.strip()]
    return jobs if jobs else ["No jobs found right now. Try another query."]

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

    # Step 1: Extract interests
    interests_text = call_mistral(system_extract, user_input)
    interests_list = []

    for i in interests_text.split(","):
        i = i.lower().replace("interests:", "").strip()
        i = interest_map.get(i, i)
        interests_list.append(i)

    # Step 2: Map to career category
    map_prompt = f"The following are the user interests: {', '.join(interests_list)}. Which category do they best fit into among STEM, Arts, Sports?"
    career_category = call_mistral(system_map, map_prompt)

    # Step 3: Explain
    explain_prompt = f"Explain why {career_category.strip()} is a good fit for someone interested in {', '.join(interests_list)}."
    explanation = call_mistral(system_explain, explain_prompt)

    # Step 4: Get job recommendations via LLM
    job_recommendations = generate_jobs_with_llm(interests_list)

    return {
        "interests": interests_list,
        "career_category": career_category,
        "explanation": explanation,
        "job_recommendations": job_recommendations
    }

# ------------------ Web Page ------------------ #
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
