"""
Update Render service env vars via API.
Requires: RENDER_API_TOKEN, RENDER_SERVICE_ID, GEMINI_API_KEY, GROQ_API_KEY
"""
import json
import os
import sys

import requests

TOKEN = os.environ.get("RENDER_API_TOKEN")
SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
GEMINI = os.environ.get("GEMINI_API_KEY")
GROQ = os.environ.get("GROQ_API_KEY")

if not all([TOKEN, SERVICE_ID, GEMINI, GROQ]):
    sys.exit(
        "Set RENDER_API_TOKEN, RENDER_SERVICE_ID, GEMINI_API_KEY, GROQ_API_KEY in the environment."
    )

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
}

env_vars = [
    {"key": "PYTHON_VERSION", "value": "3.11"},
    {"key": "GEMINI_API_KEY", "value": GEMINI},
    {"key": "GROQ_API_KEY", "value": GROQ},
]

r = requests.put(
    f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars",
    headers=HEADERS,
    json=env_vars,
)
print("Status:", r.status_code)
try:
    print("Response:", json.dumps(r.json(), indent=2))
except Exception:
    print("Response:", r.text)
