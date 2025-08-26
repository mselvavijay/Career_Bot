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
system_job_titles = "You are a career assistant. Generate 5-10 relevant job titles for a person interested in these topics."

# Optional interest normalization
interest_map = {
    "singing": "music",
    "composing music": "music",
    "coding": "programming",
    "programming": "programming",
    "fitness": "fitness",
    "painting": "painting",
    "music": "music",
    "football": "football",
    "basketball": "basketball",
    "web design": "web_design",
    "web designing": "web_design"
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
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"].strip()
        else:
            return "Error: No response from model."
    except Exception as e:
        print("Error calling Mistral:", e)
        return f"Error: {str(e)}"

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
    if "Error" not in interests_text.lower():
        for i in interests_text.split(","):
            i = i.lower().replace("interests:", "").strip()
            i = interest_map.get(i, i)
            interests_list.append(i)
    else:
        interests_list = ["Error: Could not extract interests."]

    # Step 2: Map to career category
    if "Error" not in interests_text.lower():
        map_prompt = f"The following are the user interests: {', '.join(interests_list)}. Which category do they best fit into among STEM, Arts, Sports?"
        career_category = call_mistral(system_map, map_prompt)
    else:
        career_category = "Error: Could not determine career category."

    # Step 3: Explain
    if "Error" not in career_category.lower():
        explain_prompt = f"Explain why {career_category.strip()} is a good fit for someone interested in {', '.join(interests_list)}."
        explanation = call_mistral(system_explain, explain_prompt)
    else:
        explanation = "Error: Could not generate explanation."

    # Step 4: Generate job titles using LLM
    if "Error" not in career_category.lower():
        job_titles_prompt = f"Suggest 5-10 realistic job titles for someone interested in {', '.join(interests_list)}."
        job_titles = call_mistral(system_job_titles, job_titles_prompt)
        job_titles_list = [jt.strip() for jt in job_titles.split("\n") if jt.strip()]
        if not job_titles_list:
            job_titles_list = ["No job titles found."]
    else:
        job_titles_list = ["No job titles available due to earlier errors."]

    return {
        "interests": interests_list,
        "career_category": career_category,
        "explanation": explanation,
        "job_titles": job_titles_list
    }

# ------------------ Web Page ------------------ #
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
