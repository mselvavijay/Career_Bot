import os
import requests
from dotenv import load_dotenv

# ------------------ LOAD ENV ------------------ #
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
system_extract = (
    "You are an assistant that extracts main interests from user conversations. "
    "Answer in 1-2 short phrases separated by commas."
)
system_map = (
    "You are a helpful assistant that maps interests to career paths from: STEM, Arts, Sports. "
    "Answer with only the category."
)
system_explain = "You are a career guide. Give a concise 1-2 sentence explanation for the recommended career path."

# ------------------ HELPER FUNCTIONS ------------------ #
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
    """Fetch jobs from JSearch using concise job titles only, India-specific"""
    headers = {
        "X-RapidAPI-Key": JSEARCH_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {
        "query": job_title,
        "num_pages": "1",
        "location": location,  # ensures city/country filter
        "country": "IN",       # explicitly India
        "language": "en"
    }
    response = requests.get(JSEARCH_URL, headers=headers, params=params)
    data = response.json()

    # Debug
    print(f"DEBUG: JSearch results for '{job_title}' in {location}:", data)

    jobs = []
    if "data" in data and len(data["data"]) > 0:
        for job in data["data"][:5]:
            jobs.append(f"{job['job_title']} at {job['employer_name']} ({job['job_city']})")
    return jobs


# ------------------ INTEREST TO JOB TITLES ------------------ #
interest_to_jobs = {
    # STEM / Tech
    "coding": ["Software Engineer", "Backend Developer", "Full Stack Developer", "Data Analyst"],
    "dashboards": ["Data Analyst", "BI Developer", "Dashboard Developer", "UI/UX Designer"],
    "programming": ["Software Engineer", "Mobile App Developer", "Data Engineer"],
    # Arts
    "painting": ["Graphic Designer", "Illustrator", "Animator", "Art Teacher"],
    "music": ["Music Teacher", "Composer", "Sound Designer", "Performer"],
    # Sports
    "football": ["Football Coach", "Sports Analyst", "Physical Trainer"],
    "fitness": ["Personal Trainer", "Fitness Coach", "Yoga Instructor"],
    "basketball": ["Basketball Coach", "Sports Analyst", "Athletic Trainer"]
}

# ------------------ MAIN FLOW ------------------ #
if __name__ == "__main__":
    user_input = input("Hey, tell me what you enjoy doing or learning: ")

    # Step 1: Extract interests
    interests_text = call_mistral(system_extract, user_input)

    # Step 1a: Clean and map common phrases
    interests_list = []
    for i in interests_text.split(","):
        i = i.lower().replace("interests:", "").strip()
        if "dashboard" in i or "dashboards" in i:
            i = "dashboards"
        if "coding" in i or "programming" in i:
            i = "coding"
        if "fitness" in i or "exercise" in i:
            i = "fitness"
        interests_list.append(i)

    print("\n--- Extracted Interests ---\n", interests_list)

    # Step 2: Map to category (optional, just for explanation)
    map_prompt = f"The following are the user interests: {', '.join(interests_list)}. Which category do they best fit into among STEM, Arts, Sports?"
    career_category = call_mistral(system_map, map_prompt)
    print("\n--- Mapped Career Category ---\n", career_category)

    # Step 3: Explanation
    explain_prompt = f"Explain why {career_category.strip()} is a good fit for someone interested in {', '.join(interests_list)}."
    explanation = call_mistral(system_explain, explain_prompt)
    print("\n--- Explanation ---\n", explanation)

    # Step 4: Fetch jobs based on individual interests
    all_jobs = []
    for interest in interests_list:
        job_titles = interest_to_jobs.get(interest, [])
        for title in job_titles:
            all_jobs += get_jobs_from_jsearch(title)

    # Remove duplicates
    all_jobs = list(dict.fromkeys(all_jobs))

    # Step 5: Display jobs
    print("\n--- Job Recommendations ---")
    if all_jobs:
        for job in all_jobs:
            print("-", job)
    else:
        print("- No jobs found right now. Try another query.")
