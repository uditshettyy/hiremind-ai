import asyncio
import traceback
from fastapi.testclient import TestClient
from app.main import app

def main():
    client = TestClient(app)
    payload = {
        "candidate_id": "c1",
        "job_id": "j1",
        "resume_text": "Experienced Python and Fastapi backend developer with 4 years experience.",
        "parsed_jd": {
            "title": "Backend Developer",
            "company": "Tech Corp",
            "requirements": [
                {
                    "skill_name": "Python",
                    "category": "technical",
                    "required_level": "proficient",
                    "priority": 5,
                    "evidence": "Must know Python"
                },
                {
                    "skill_name": "Kubernetes",
                    "category": "infrastructure",
                    "required_level": "expert",
                    "priority": 4,
                    "evidence": "Must have expert knowledge of Kubernetes"
                }
            ],
            "responsibilities": ["Deploy backend services"],
            "raw_text": "Job description text..."
        }
    }
    try:
        response = client.post("/analyze/skill-gap", json=payload)
        print("Status code:", response.status_code)
        print("Response body:", response.text)
    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    main()
