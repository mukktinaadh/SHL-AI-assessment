import json
import os
import sys

import requests

TOKEN = os.environ.get("RENDER_API_TOKEN")
if not TOKEN:
    sys.exit("Set RENDER_API_TOKEN in the environment.")

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {TOKEN}",
}

r = requests.get("https://api.render.com/v1/owners", headers=HEADERS)
if r.status_code == 200:
    owners = r.json()
    print("Owners:", owners)
    owner_id = owners[0]["owner"]["id"]
    print(f"Using Owner ID: {owner_id}")
else:
    print("Failed to get owners:", r.text)
