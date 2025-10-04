# Created with ChatGPT

import requests, hmac, hashlib
from fastapi import FastAPI, Request
import uvicorn

# Twitch app credentials (make a Twitch dev app)
CLIENT_ID = "your_twitch_client_id"
CLIENT_SECRET = "your_twitch_client_secret"

# Discord webhook URL (channel you want to notify)
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/.../... "

# Secret used to validate Twitch signatures
SECRET = b"supersecret"

CALLBACK_URL = "https://yourdomain.com/twitch/callback"

app = FastAPI()

# --- Twitch setup ---
def get_app_token():
    r = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    })
    return r.json()["access_token"]

ACCESS_TOKEN = get_app_token()

def get_user_id(login):
    r = requests.get("https://api.twitch.tv/helix/users",
                     headers={"Client-ID": CLIENT_ID,
                              "Authorization": f"Bearer {ACCESS_TOKEN}"},
                     params={"login": login})
    data = r.json()["data"]
    return data[0]["id"], data[0]["display_name"]

def subscribe(user_id):
    body = {
        "type": "stream.online",
        "version": "1",
        "condition": {"broadcaster_user_id": user_id},
        "transport": {
            "method": "webhook",
            "callback": CALLBACK_URL,
            "secret": SECRET.decode()
        }
    }
    requests.post("https://api.twitch.tv/helix/eventsub/subscriptions",
                  headers={"Client-ID": CLIENT_ID,
                           "Authorization": f"Bearer {ACCESS_TOKEN}",
                           "Content-Type": "application/json"},
                  json=body)

# --- Signature verification ---
def verify_signature(request: Request, body: bytes):
    msg_id = request.headers["Twitch-Eventsub-Message-Id"]
    timestamp = request.headers["Twitch-Eventsub-Message-Timestamp"]
    signature = request.headers["Twitch-Eventsub-Message-Signature"]
    msg = msg_id + timestamp + body.decode()
    h = "sha256=" + hmac.new(SECRET, msg.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(h, signature)

# --- FastAPI route ---
@app.post("/twitch/callback")
async def twitch_callback(request: Request):
    body = await request.body()
    data = await request.json()

    if not verify_signature(request, body):
        return {"status": "unauthorized"}

    msg_type = request.headers["Twitch-Eventsub-Message-Type"]

    if msg_type == "webhook_callback_verification":
        return data["challenge"]

    if data["subscription"]["type"] == "stream.online":
        user = data["event"]["broadcaster_user_name"]
        url = f"https://twitch.tv/{user}"
        requests.post(DISCORD_WEBHOOK, json={"content": f"{user} is live! {url}"})
        print(f"{user} is live!")

    return {"ok": True}

# --- Entry ---
if __name__ == "__main__":
    with open("twitch_users.txt") as f:
        for login in f:
            login = login.strip()
            if not login: continue
            uid, display = get_user_id(login)
            subscribe(uid)
            print(f"Subscribed to {display}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
