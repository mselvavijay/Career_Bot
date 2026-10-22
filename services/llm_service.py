import os
import json
import httpx
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

# Check for Groq first, then OpenRouter
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if GROQ_API_KEY:
    API_KEY = GROQ_API_KEY
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    DEFAULT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
else:
    API_KEY = OPENROUTER_API_KEY
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_MODEL = "mistralai/mistral-7b-instruct"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

SYSTEM_PROMPT_TEMPLATE = """You are an expert Executive AI Career Counselor and Talent Intelligence Advisor.
You converse naturally with the candidate across multiple turns, taking into account their user profile (education, skills, interests, current role) and entire conversation context to deliver deeply personalized career recommendations and active job opportunities.

CRITICAL INSTRUCTION:
You must ALWAYS respond with ONLY a valid JSON object and nothing else. No markdown wrappers, no backticks, no explanatory text outside the JSON.

Expected JSON format:
{{
  "reply": "Your conversational response directly addressing the user's latest input, asking clarifying questions, acknowledging context, or summarizing strategic career guidance.",
  "interests": ["Identified Focus Area 1", "Identified Focus Area 2"],
  "career_category": "STEM" | "Arts" | "Sports" | "Business" | "Healthcare" | "Other",
  "explanation": "A concise 1-2 sentence explanation connecting the candidate's background/skills/interests to the recommended category.",
  "job_titles": ["Job Title 1", "Job Title 2", "Job Title 3"],
  "open_jobs": [
    {{
      "title": "Exact Role Title (e.g. Machine Learning Engineer)",
      "company": "Target Hiring Organization or Industry Sector (e.g. OpenAI / Cloudflare / Enterprise AI Labs)",
      "location": "Location & Work Mode (e.g. Remote / Hybrid / Bangalore / San Francisco)",
      "job_type": "Full-time" | "Contract" | "Internship",
      "salary_range": "Estimated Market Compensation (e.g. ₹10,00,000 - ₹18,00,000 / $85,000 - $125,000)",
      "skills_required": ["Primary Skill 1", "Skill 2", "Skill 3"],
      "description": "1-2 sentence summary of core mission, responsibilities, and key qualifications.",
      "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Machine+Learning+Engineer"
    }}
  ]
}}

Guidelines:
- Provide 3 to 5 realistic, high-quality open job listings matching the candidate's career trajectory in "open_jobs".
- Include realistic salary expectations and key required skills.
- Make the "apply_url" a direct search query to LinkedIn Jobs or Google Jobs for that specific role title.
- Keep the tone professional, encouraging, and authoritative.
"""

def format_job_card(title: str, category: str = "Technology") -> dict:
    clean_title = title.split(".", 1)[-1].strip() if "." in title[:3] else title.strip()
    encoded = clean_title.replace(" ", "+")
    return {
        "title": clean_title,
        "company": f"Leading {category} Organizations",
        "location": "Remote / Hybrid",
        "job_type": "Full-time",
        "salary_range": "Competitive Market Compensation",
        "skills_required": [clean_title, "Problem Solving", "System Design"],
        "description": f"Active hiring opening seeking qualified professionals in {clean_title}.",
        "apply_url": f"https://www.linkedin.com/jobs/search/?keywords={encoded}"
    }

def sanitize_and_enrich_jobs(parsed: dict) -> dict:
    category = parsed.get("career_category", "Technology")
    open_jobs = parsed.get("open_jobs", [])
    job_titles = parsed.get("job_titles", [])

    enriched_jobs = []
    if isinstance(open_jobs, list):
        for j in open_jobs:
            if isinstance(j, dict) and j.get("title"):
                title = j["title"].strip()
                company = j.get("company") or f"Top {category} Employer"
                location = j.get("location") or "Remote / Hybrid"
                job_type = j.get("job_type") or "Full-time"
                salary = j.get("salary_range") or "Competitive Compensation"
                skills = j.get("skills_required") or [title]
                desc = j.get("description") or f"Exciting position for an ambitious {title}."
                apply_url = j.get("apply_url")
                if not apply_url or not apply_url.startswith("http"):
                    apply_url = f"https://www.linkedin.com/jobs/search/?keywords={title.replace(' ', '+')}"

                enriched_jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_type": job_type,
                    "salary_range": salary,
                    "skills_required": skills if isinstance(skills, list) else [str(skills)],
                    "description": desc,
                    "apply_url": apply_url
                })

    # If open_jobs was empty, build from job_titles
    if not enriched_jobs and isinstance(job_titles, list):
        for title in job_titles[:5]:
            if isinstance(title, str) and title.strip():
                enriched_jobs.append(format_job_card(title, category))

    # If still empty, provide general roles based on category
    if not enriched_jobs:
        default_titles = [f"{category} Specialist", f"Associate {category} Lead", f"Senior {category} Consultant"]
        for dt in default_titles:
            enriched_jobs.append(format_job_card(dt, category))

    parsed["open_jobs"] = enriched_jobs
    # Also sync job_titles as list of strings
    parsed["job_titles"] = [j["title"] for j in enriched_jobs]
    return parsed

def build_system_message(user_profile: Optional[Dict[str, Any]] = None) -> str:
    prompt = SYSTEM_PROMPT_TEMPLATE
    if user_profile:
        profile_parts = []
        if user_profile.get("name"):
            profile_parts.append(f"Name: {user_profile['name']}")
        if user_profile.get("education"):
            profile_parts.append(f"Education: {user_profile['education']}")
        if user_profile.get("current_role"):
            profile_parts.append(f"Current Role: {user_profile['current_role']}")
        if user_profile.get("skills"):
            profile_parts.append(f"Skills: {user_profile['skills']}")
        if user_profile.get("interests"):
            profile_parts.append(f"Declared Profile Interests: {user_profile['interests']}")
        if user_profile.get("target_industry"):
            profile_parts.append(f"Target Industry: {user_profile['target_industry']}")

        if profile_parts:
            prompt += "\n\nACTIVE CANDIDATE PROFILE CONTEXT:\n" + "\n".join(profile_parts)
    return prompt


async def analyze_conversation_turn(
    user_input: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    user_profile: Optional[Dict[str, Any]] = None
) -> dict:
    """
    Context-aware multi-turn analysis.
    Builds the message list with system prompt, user profile, past dialogue turns (sliding window),
    and the latest input. Returns structured JSON parsed into a python dictionary with guaranteed open_jobs.
    """
    system_prompt = build_system_message(user_profile)
    messages = [{"role": "system", "content": system_prompt}]

    # Context management: retain the last 8 messages (4 turns) to balance context depth & token cost
    if conversation_history:
        recent_history = conversation_history[-8:]
        for msg in recent_history:
            role = "assistant" if msg.get("role") == "assistant" else "user"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})

    # Append current turn
    messages.append({"role": "user", "content": user_input})

    payload = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.5,
        "response_format": {"type": "json_object"}
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(BASE_URL, headers=HEADERS, json=payload)
            response.raise_for_status()
            result = response.json()

            if "choices" not in result or len(result["choices"]) == 0:
                raise HTTPException(status_code=502, detail="Invalid response from LLM model.")

            raw_content = result["choices"][0]["message"]["content"].strip()

            # Clean any possible markdown code fence ```json ... ``` wrapper
            if raw_content.startswith("```"):
                raw_lines = raw_content.splitlines()
                if raw_lines[0].startswith("```"):
                    raw_lines = raw_lines[1:]
                if raw_lines and raw_lines[-1].startswith("```"):
                    raw_lines = raw_lines[:-1]
                raw_content = "\n".join(raw_lines).strip()

            parsed = json.loads(raw_content)

            # Ensure all required keys exist
            if "reply" not in parsed:
                parsed["reply"] = parsed.get("explanation", "Here are your career recommendations.")
            if "interests" not in parsed or not isinstance(parsed["interests"], list):
                parsed["interests"] = []
            if "career_category" not in parsed:
                parsed["career_category"] = "Professional & Technology"

            return sanitize_and_enrich_jobs(parsed)

    except json.JSONDecodeError:
        # Fallback if model returned plain conversational text instead of strict JSON
        fallback = {
            "reply": raw_content if 'raw_content' in locals() else "I received your message.",
            "interests": [],
            "career_category": "Professional & Technology",
            "explanation": "Recommendations aligned with your skills and background.",
            "job_titles": ["Software Engineer", "Solutions Architect", "Data Analyst"]
        }
        return sanitize_and_enrich_jobs(fallback)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with LLM: {str(e)}")


# Backward compatibility wrapper for old single-turn calls
async def analyze_user_input(user_input: str) -> dict:
    return await analyze_conversation_turn(user_input=user_input)
