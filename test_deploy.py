import json
import os
import sys

import requests

TOKEN = os.environ.get("RENDER_API_TOKEN")
SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
if not TOKEN or not SERVICE_ID:
    sys.exit("Set RENDER_API_TOKEN and RENDER_SERVICE_ID in the environment.")

HEADERS = {"Authorization": f"Bearer {TOKEN}"}

r = requests.get(
    f"https://api.render.com/v1/services/{SERVICE_ID}/deploys?limit=1",
    headers=HEADERS,
)
if r.status_code == 200:
    print(json.dumps(r.json(), indent=2))
else:
    print(r.text)
