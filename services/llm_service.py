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

SYSTEM_PROMPT_TEMPLATE = """You are an expert AI Career Counselor and Talent Intelligence Advisor specializing exclusively in the INDIAN Job Market.
You converse directly with the candidate, leveraging their declared user profile (Degree, Years of Experience, Technical Skills) to deliver tailored job recommendations in India along with structured 3-Week Preparation Guides.

CRITICAL INSTRUCTIONS FOR BASIC PLAN:
1. RECENCY & LOCATION: Recommend only India-based Hybrid or Remote jobs posted within the last 7 days. Provide a LinkedIn search URL for each role; never include company names.
2. COMPENSATION: Express all salary ranges in Indian Rupees LPA (Lakhs Per Annum, e.g. ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹6 - ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹10 LPA, ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹12 - ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹20 LPA, ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹22 - ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹38 LPA) matching candidate experience.
3. 10 JOB OPENINGS: You must ALWAYS provide EXACTLY 10 job openings in the "open_jobs" array.
4. 3-WEEK PREPARATION GUIDE: For EACH of the 10 job openings, you must include a "prep_guide" array of EXACTLY 3 concise bullet points:
   - "Week 1: [DSA, Core Fundamentals & Language Concepts]"
   - "Week 2: [Key Frameworks, Databases & Live Project Implementation]"
   - "Week 3: [System Design, Mock Technical Interviews & Behavioral Rounds]"
5. NO VERBOSE / LONG ESSAYS: Keep job descriptions to 1 concise sentence. Keep prep guide items as sharp, actionable bullets.
6. CANDIDATE PROFILE GROUNDING: When the candidate's profile is saved, DO NOT speculate about generic career categories (e.g. Arts vs Sports). Directly provide role intelligence and the 10 jobs strictly matching their declared Degree, Experience, and Skills.
7. CRITICAL JSON FORMAT: You must ALWAYS respond with ONLY a valid JSON object. No markdown wrappers, no backticks outside JSON.

Expected JSON format:
{{
  "reply": "Concise 2-3 sentence strategic summary acknowledging the candidate's degree, experience, and skills, introducing the 10 Indian job recommendations and prep roadmaps.",
  "interests": ["Skill/Domain 1", "Skill/Domain 2"],
  "career_category": "Technology",
  "explanation": "Brief 1-sentence alignment with candidate profile.",
  "job_titles": ["Job 1", "Job 2", "Job 3", "Job 4", "Job 5", "Job 6", "Job 7", "Job 8", "Job 9", "Job 10"],
  "open_jobs": [
    {{
      "title": "Exact Role Title (e.g. Backend Developer - Python)",
      "company": "Indian Tech Company or MNC Hub (e.g. Swiggy / Flipkart / Razorpay / PhonePe / Infosys)",
      "location": "City in India (e.g. Bangalore, Karnataka / Remote India)",
      "job_type": "Full-time",
      "salary_range": "ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹8,00,000 - ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹14,00,000 LPA",
      "skills_required": ["Python", "FastAPI", "PostgreSQL"],
      "description": "High-impact opening focusing on scalable microservices and APIs.",
      "prep_guide": [
        "Week 1: DSA in Python, time-complexity analysis, and core concurrency patterns.",
        "Week 2: FastAPI / Django REST microservice build, Dockerization, and SQL indexing.",
        "Week 3: Low-Level System Design, Mock API problem-solving, and resume walkthrough."
      ],
      "apply_url": "https://www.linkedin.com/jobs/search/?keywords=Backend+Developer+Python&location=India"
    }}
  ]
}}

MANDATORY TRI-FACTOR CALIBRATION RULES (EXPERIENCE + SKILLS + DEGREE):
1. YEARS OF EXPERIENCE (Calibrates Seniority, Hierarchy & LPA in India):
   * 0 Years / Fresher / Student: STRICTLY suggest Entry-Level, Graduate, Junior, or Intern roles (e.g., Junior Python Engineer, Associate AI Developer, Graduate Software Engineer). Target ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹4 - ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹9 LPA. NEVER recommend Senior or Lead roles.
   * 1-3 Years: Junior to Mid-Level software roles (ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹8 - ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹16 LPA).
   * 4-7 Years: Mid-Senior, Specialist, or Technical Lead roles (ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹18 - ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹32 LPA).
   * 8+ Years: Senior Staff, Principal, or Engineering Manager roles (ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹35 - ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¹60+ LPA).
2. CORE SKILLS: The 10 roles must directly utilize the candidate's declared programming languages, frameworks, and domain competencies.
3. DEGREE: Ensure academic alignment (e.g. B.Tech / B.E., M.S., BCA, MCA, B.Sc) with industry prerequisites.
"""

INDIAN_TECH_HUBS = [
    "Bangalore, Karnataka", "Hyderabad, Telangana", "Pune, Maharashtra",
    "Gurgaon, Delhi NCR", "Mumbai, Maharashtra", "Noida, Uttar Pradesh",
    "Chennai, Tamil Nadu", "Remote (India)", "Bangalore / Hybrid", "Gurgaon / Hybrid"
]

INDIAN_COMPANIES = [
    "Flipkart", "Swiggy", "Zomato", "Razorpay", "PhonePe",
    "Zepto", "CRED", "Infosys Digital", "TCS Enterprise", "Jio Platforms",
    "Microsoft India", "Amazon India", "Google India", "Groww", "Paytm"
]

def format_job_card(title: str, category: str = "Technology", exp_years: int = 0, index: int = 0) -> dict:
    clean_title = title.split(".", 1)[-1].strip() if "." in title[:3] else title.strip()
    encoded = clean_title.replace(" ", "+")
    company = INDIAN_COMPANIES[index % len(INDIAN_COMPANIES)]
    location = INDIAN_TECH_HUBS[index % len(INDIAN_TECH_HUBS)]

    if exp_years == 0:
        salary = "5 - 9 LPA"
    elif exp_years <= 3:
        salary = "8 - 16 LPA"
    elif exp_years <= 7:
        salary = "18 - 32 LPA"
    else:
        salary = "35 - 60 LPA"

    return {
        "title": clean_title,
        "company": company,
        "location": location,
        "job_type": "Full-time",
        "salary_range": salary,
        "skills_required": [clean_title, "Problem Solving", "Data Structures"],
        "description": f"Active hiring opportunity in {location} for qualified {clean_title}.",
        "prep_guide": [
            f"Week 1: Algorithmic problem-solving (DSA) & Core Computer Science concepts for {clean_title}.",
            f"Week 2: Deep dive into core frameworks, databases, and building a showcase project.",
            f"Week 3: Low-Level & High-Level System Design, mock interviews, and live coding practice."
        ],
        "apply_url": f"https://www.linkedin.com/jobs/search/?keywords={encoded}&location=India"
    }

def sanitize_and_enrich_jobs(parsed: dict, user_profile: Optional[Dict[str, Any]] = None) -> dict:
    category = parsed.get("career_category", "Technology")
    open_jobs = parsed.get("open_jobs", [])
    job_titles = parsed.get("job_titles", [])

    exp_years = 0
    if user_profile and user_profile.get("years_of_experience"):
        try:
            import re
            m = re.search(r'\d+', str(user_profile.get("years_of_experience")))
            if m:
                exp_years = int(m.group())
        except Exception:
            exp_years = 0

    enriched_jobs = []
    if isinstance(open_jobs, list):
        for idx, j in enumerate(open_jobs):
            if isinstance(j, dict) and j.get("title"):
                title = j["title"].strip()
                company = ""
                location = "India"
                if "India" not in location and not any(h in location for h in ["Bangalore", "Hyderabad", "Pune", "Mumbai", "Delhi", "Gurgaon", "Noida", "Chennai"]):
                    location = f"{location} (India)"
                job_type = "Remote" if "remote" in str(j.get("job_type", "")).lower() else "Hybrid"
                salary = "5 - 9 LPA" if exp_years == 0 else ("8 - 16 LPA" if exp_years <= 3 else ("18 - 32 LPA" if exp_years <= 7 else "35 - 60 LPA"))
                skills = j.get("skills_required") or [title]
                desc = j.get("description") or f"Active position for {title} in India."

                prep_guide = j.get("prep_guide")
                if not isinstance(prep_guide, list) or len(prep_guide) < 3:
                    prep_guide = [
                        f"Week 1: Core Fundamentals, DSA problem solving, and language fluency for {title}.",
                        f"Week 2: Primary tech stack, API architecture, and real-world project deployment.",
                        f"Week 3: System Design, technical mock interviews, and scenario-based problem solving."
                    ]

                apply_url = j.get("apply_url")
                if not apply_url or not apply_url.startswith("http"):
                    apply_url = f"https://www.linkedin.com/jobs/search/?keywords={title.replace(' ', '+')}&location=India"

                enriched_jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_type": job_type,
                    "salary_range": salary,
                    "skills_required": skills if isinstance(skills, list) else [str(skills)],
                    "description": desc,
                    "prep_guide": prep_guide,
                    "apply_url": apply_url
                })

    # Fill up to 10 jobs if fewer than 10 returned
    if len(enriched_jobs) < 10:
        seen_titles = {j["title"].lower() for j in enriched_jobs}
        # Check job_titles first
        if isinstance(job_titles, list):
            for t in job_titles:
                if isinstance(t, str) and t.strip() and t.strip().lower() not in seen_titles:
                    enriched_jobs.append(format_job_card(t.strip(), category, exp_years, len(enriched_jobs)))
                    seen_titles.add(t.strip().lower())
                    if len(enriched_jobs) >= 10:
                        break

    # If still fewer than 10, fill with calibrated Indian tech roles
    if len(enriched_jobs) < 10:
        prefix = "Junior" if exp_years == 0 else ("Senior" if exp_years >= 5 else "Mid-Level")
        base_skill = "Software"
        if user_profile and user_profile.get("skills"):
            first_skill = user_profile.get("skills").split(",")[0].strip()
            if first_skill:
                base_skill = first_skill

        sample_titles = [
            f"{base_skill} Backend Engineer",
            f"Associate {base_skill} Developer",
            f"Full Stack {base_skill} Specialist",
            f"Cloud & DevOps Engineer ({base_skill})",
            f"Systems Engineer - {base_skill}",
            f"API & Platform Engineer ({base_skill})",
            f"{prefix} Application Developer",
            f"{base_skill} Integration Engineer",
            f"Data & Backend Specialist ({base_skill})",
            f"Core {base_skill} Solutions Engineer"
        ]
        for st in sample_titles:
            if st.lower() not in seen_titles and len(enriched_jobs) < 10:
                enriched_jobs.append(format_job_card(st, category, exp_years, len(enriched_jobs)))
                seen_titles.add(st.lower())

    parsed["open_jobs"] = enriched_jobs[:10]
    parsed["job_titles"] = [j["title"] for j in enriched_jobs[:10]]
    return parsed

def build_system_message(user_profile: Optional[Dict[str, Any]] = None) -> str:
    prompt = SYSTEM_PROMPT_TEMPLATE
    if user_profile:
        profile_parts = []
        if user_profile.get("name"):
            profile_parts.append(f"Candidate Name: {user_profile['name']}")
        if user_profile.get("education"):
            profile_parts.append(f"Degree / Education: {user_profile['education']} (Academic foundation & qualification requirements)")
        if user_profile.get("years_of_experience") is not None and str(user_profile.get("years_of_experience")).strip():
            profile_parts.append(f"Years of Experience: {user_profile['years_of_experience']} (Seniority level: strictly match role level to this experience)")
        if user_profile.get("skills"):
            profile_parts.append(f"Core Competencies & Skills: {user_profile['skills']} (Derive technical specialization and matching job titles directly from these skills)")
        if user_profile.get("current_role"):
            profile_parts.append(f"Current Role / Stage: {user_profile['current_role']}")

        if profile_parts:
            prompt += "\n\nACTIVE CANDIDATE PROFILE (TRI-FACTOR CONTEXT: EXPERIENCE + SKILLS + DEGREE):\n" + "\n".join(profile_parts)
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

            return sanitize_and_enrich_jobs(parsed, user_profile)

    except json.JSONDecodeError:
        # Fallback if model returned plain conversational text instead of strict JSON
        fallback = {
            "reply": raw_content if 'raw_content' in locals() else "I received your message.",
            "interests": [],
            "career_category": "Professional & Technology",
            "explanation": "Recommendations aligned with your skills and background.",
            "job_titles": ["Software Engineer", "Backend Developer", "Full Stack Engineer"]
        }
        return sanitize_and_enrich_jobs(fallback, user_profile)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with LLM: {str(e)}")


# Backward compatibility wrapper for old single-turn calls
async def analyze_user_input(user_input: str) -> dict:
    return await analyze_conversation_turn(user_input=user_input)
