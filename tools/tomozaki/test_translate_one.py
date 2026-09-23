import urllib.request
import json
from pathlib import Path

KEY_FILE = Path("/home/anng/Documents/data_api.txt")
with open(KEY_FILE) as f:
    keys = [l.strip() for l in f if l.strip() and not l.startswith('#')]

key = keys[0]
model = "gemini-2.5-flash" # let's test fast model or gemini-1.5-flash
# Let's test endpoint
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
try:
    resp = urllib.request.urlopen(url)
    data = json.loads(resp.read().decode())
    model_names = [m['name'].replace('models/', '') for m in data.get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', [])]
    print("Supported models sample:", [m for m in model_names if 'flash' in m or 'pro' in m][:10])
except Exception as e:
    print("Error:", e)
