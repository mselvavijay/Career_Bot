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

# ------------------ Helper Functions ------------------ #
def call_mistral(system_msg, user_msg):
    """Call Mistral LLM via OpenRouter."""
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
        return "Error: Could not call model."

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
    interests_list = [i.strip().lower() for i in interests_text.split(",")]

    # Step 2: Map to career category
    map_prompt = f"The following are the user interests: {', '.join(interests_list)}. Which category do they best fit into among STEM, Arts, Sports?"
    career_category = call_mistral(system_map, map_prompt)

    # Step 3: Explain career category
    explain_prompt = f"Explain why {career_category.strip()} is a good fit for someone interested in {', '.join(interests_list)}."
    explanation = call_mistral(system_explain, explain_prompt)

    # Step 4: Generate job titles using LLM
    jobs_prompt = f"Generate 5-10 job titles for someone interested in: {', '.join(interests_list)}."
    job_titles_text = call_mistral(system_job_titles, jobs_prompt)
    # Convert to list by splitting on newlines or commas
    job_titles_list = [j.strip("- ").strip() for j in job_titles_text.replace("\n", ",").split(",") if j.strip()]

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
