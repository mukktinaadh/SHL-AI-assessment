import json
import os
import sys

import requests

TOKEN = os.environ.get("RENDER_API_TOKEN")
if not TOKEN:
    sys.exit("Set RENDER_API_TOKEN in the environment.")

URL = "https://mcp.render.com/mcp"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {},
}

try:
    r = requests.post(URL, headers=HEADERS, json=payload)
    print("Status:", r.status_code)
    print("Response:", json.dumps(r.json(), indent=2))
except Exception as e:
    print("Error:", e)
