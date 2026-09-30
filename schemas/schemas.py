from pydantic import BaseModel
from typing import List

class CareerRequest(BaseModel):
    user_input: str

class CareerResponse(BaseModel):
    interests: List[str]
    career_category: str
    explanation: str
    job_titles: List[str]
