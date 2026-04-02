import requests
import webbrowser
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
# ===============================
# CONFIG
# ===============================
API_KEY = "12209892-be47-4120-8117-34a6e28a4e4c"
API_SECRET = "s4t3349kw5"
# API_KEY = os.getenv("f37d21cc-ddfd-4202-98e5-86aa998e6a91")
# API_SECRET = os.getenv("4thobro9zm")
REDIRECT_URI = "http://localhost:5000/callback"



AUTH_CODE = None

# ===============================
# STEP 1 — OPEN LOGIN URL
# ===============================
login_url = (
    f"https://api.upstox.com/v2/login/authorization/dialog"
    f"?response_type=code"
    f"&client_id={API_KEY}"
    f"&redirect_uri={REDIRECT_URI}"
)

print("Opening browser for login...")
webbrowser.open(login_url)

# ===============================
# STEP 2 — CAPTURE AUTH CODE
# ===============================
class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global AUTH_CODE

        if "code=" in self.path:
            AUTH_CODE = self.path.split("code=")[1]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Login successful. You can close this window.")

            print("Authorization code received.", {AUTH_CODE})
        else:
            self.send_response(400)
            self.end_headers()

server = HTTPServer(("localhost", 5000), AuthHandler)
server.handle_request()

# ===============================
# STEP 3 — EXCHANGE FOR ACCESS TOKEN
# ===============================
token_url = "https://api.upstox.com/v2/login/authorization/token"

payload = {
    "code": AUTH_CODE,
    "client_id": API_KEY,
    "client_secret": API_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code"
}

headers = {
    "accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded"
}

response = requests.post(token_url, data=payload, headers=headers)
token_data = response.json()

if "access_token" in token_data:
    access_token = token_data["access_token"]

    with open("token.json", "w") as f:
        json.dump(token_data, f, indent=4)
    for key, value in token_data.items():
        print(f"{key}: {value}")
    print("\nAccess token saved to token.json")
    print("Copy and paste it into strategy.py")
else:
    print("Token generation failed:")
    print(token_data)

