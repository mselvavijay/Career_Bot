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

SYSTEM_PROMPT_TEMPLATE = """You are an expert AI Career Counselor and Advisor.
You converse naturally with the user across multiple turns, taking into account their user profile and entire conversation context to deliver deeply personalized career recommendations.

CRITICAL INSTRUCTION:
You must ALWAYS respond with ONLY a valid JSON object and nothing else. No markdown wrappers, no backticks, no explanatory text outside the JSON.

Expected JSON format:
{{
  "reply": "Your natural conversational response directly addressing the user's latest input, asking clarifying questions, acknowledging context, or summarizing guidance.",
  "interests": ["interest 1", "interest 2"],
  "career_category": "STEM" | "Arts" | "Sports" | "Business" | "Healthcare" | "Other",
  "explanation": "A concise 1-2 sentence explanation connecting the user's background/skills/interests to the recommended category.",
  "job_titles": ["Job Title 1", "Job Title 2", "Job Title 3", "Job Title 4", "Job Title 5"]
}}

Guidelines:
- If the user is just saying hello or asking general questions, give a warm reply in "reply", list whatever broad interests or categories apply, and offer relevant initial job titles.
- When recommendations are updated or refined based on new context, reflect that in "career_category", "job_titles", and "explanation".
"""

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
            prompt += "\n\nACTIVE USER PROFILE CONTEXT:\n" + "\n".join(profile_parts)
    return prompt


async def analyze_conversation_turn(
    user_input: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    user_profile: Optional[Dict[str, Any]] = None
) -> dict:
    """
    Context-aware multi-turn analysis.
    Builds the message list with system prompt, user profile, past dialogue turns (sliding window),
    and the latest input. Returns structured JSON parsed into a python dictionary.
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
            if "job_titles" not in parsed or not isinstance(parsed["job_titles"], list):
                parsed["job_titles"] = []

            return parsed

    except json.JSONDecodeError:
        # Fallback if model returned plain conversational text instead of strict JSON
        return {
            "reply": raw_content if 'raw_content' in locals() else "I received your message.",
            "interests": [],
            "career_category": "General",
            "explanation": "Recommendations based on conversational context.",
            "job_titles": []
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with LLM: {str(e)}")


# Backward compatibility wrapper for old single-turn calls
async def analyze_user_input(user_input: str) -> dict:
    return await analyze_conversation_turn(user_input=user_input)
