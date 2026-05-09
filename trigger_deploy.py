import json
import os
import sys

import requests

TOKEN = os.environ.get("RENDER_API_TOKEN")
SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
if not TOKEN or not SERVICE_ID:
    sys.exit("Set RENDER_API_TOKEN and RENDER_SERVICE_ID in the environment.")

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
}

payload = {"clearCache": "do_not_clear"}

r = requests.post(
    f"https://api.render.com/v1/services/{SERVICE_ID}/deploys",
    headers=HEADERS,
    json=payload,
)
print("Status:", r.status_code)
try:
    print("Response:", json.dumps(r.json(), indent=2))
except Exception:
    print("Response:", r.text)
