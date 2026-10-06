import os
import json
import httpx
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Single combined system prompt — replaces 4 separate LLM calls
SYSTEM_COMBINED = """You are an expert career advisor. 
When given a user message describing their interests, you MUST respond with ONLY a valid JSON object and nothing else. No explanation, no markdown.

The JSON format must be:
{
  "interests": ["interest1", "interest2"],
  "career_category": "STEM" | "Arts" | "Sports",
  "explanation": "A concise 1-2 sentence explanation of why this career category fits.",
  "job_titles": ["Job Title 1", "Job Title 2", "Job Title 3", "Job Title 4", "Job Title 5"]
}"""


async def analyze_user_input(user_input: str) -> dict:
    """
    Makes a SINGLE async call to the LLM and returns a structured dict.
    Replaces the previous 4 sequential blocking calls.
    """
    data = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [
            {"role": "system", "content": SYSTEM_COMBINED},
            {"role": "user", "content": user_input}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(BASE_URL, headers=HEADERS, json=data)
            response.raise_for_status()
            result = response.json()

            if "choices" not in result or len(result["choices"]) == 0:
                raise HTTPException(status_code=502, detail="Invalid response from LLM model.")

            raw_content = result["choices"][0]["message"]["content"].strip()

            # Parse the JSON returned by the LLM
            parsed = json.loads(raw_content)
            return parsed

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"LLM returned invalid JSON: {str(e)}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with LLM: {str(e)}")
