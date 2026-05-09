"""
One-off helper: create a Render web service via API.
Requires env: RENDER_API_TOKEN, RENDER_OWNER_ID, GEMINI_API_KEY, GROQ_API_KEY
Never commit real keys — GitHub push protection will block the repo.
"""
import json
import os
import sys

import requests

TOKEN = os.environ.get("RENDER_API_TOKEN")
OWNER_ID = os.environ.get("RENDER_OWNER_ID")
GEMINI = os.environ.get("GEMINI_API_KEY")
GROQ = os.environ.get("GROQ_API_KEY")

if not all([TOKEN, OWNER_ID, GEMINI, GROQ]):
    sys.exit(
        "Set RENDER_API_TOKEN, RENDER_OWNER_ID, GEMINI_API_KEY, GROQ_API_KEY in the environment."
    )

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
}

payload = {
    "type": "web_service",
    "name": "shl-assessment-recommender",
    "ownerId": OWNER_ID,
    "repo": "https://github.com/mukktinaadh/SHL-AI-assessment",
    "autoDeploy": "yes",
    "branch": "main",
    "serviceDetails": {
        "env": "python",
        "region": "oregon",
        "plan": "free",
        "envSpecificDetails": {
            "buildCommand": "pip install -r backend/requirements.txt && cd backend && python scraper.py && python scripts/build_index.py",
            "startCommand": "cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT",
        },
        "envVars": [
            {"key": "GEMINI_API_KEY", "value": GEMINI},
            {"key": "GROQ_API_KEY", "value": GROQ},
            {"key": "PYTHON_VERSION", "value": "3.11"},
        ],
    },
}

r = requests.post("https://api.render.com/v1/services", headers=HEADERS, json=payload)
print("Status:", r.status_code)
try:
    print("Response:", json.dumps(r.json(), indent=2))
except Exception:
    print("Response:", r.text)
