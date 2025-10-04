import os
import requests
import hmac
import hashlib
from fastapi import FastAPI, Request
import uvicorn

# --- REQUIRED ENVIRONMENT VARIABLES (set these before running) ---
# TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, DISCORD_WEBHOOK, CALLBACK_URL
# Optional: SECRET (default: "supersecret")
CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]
CALLBACK_URL = os.environ["CALLBACK_URL"]
SECRET = os.environ.get("SECRET", "supersecret").encode()

app = FastAPI()

def get_app_token():
    r = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    })
    r.raise_for_status()
    return r.json()["access_token"]

ACCESS_TOKEN = get_app_token()
HEADERS = {"Client-ID": CLIENT_ID, "Authorization": f"Bearer {ACCESS_TOKEN}"}

def get_user_id(login):
    r = requests.get("https://api.twitch.tv/helix/users", headers=HEADERS, params={"login": login})
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        raise ValueError(f"user not found: {login}")
    return data[0]["id"], data[0].get("display_name", login), data[0].get("login", login)

def subscribe_stream_online(user_id):
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
    r = requests.post("https://api.twitch.tv/helix/eventsub/subscriptions",
                      headers={**HEADERS, "Content-Type": "application/json"},
                      json=body)
    # don't fail hard here; print result for debugging
    try:
        print("subscribe response:", r.status_code, r.json())
    except Exception:
        print("subscribe status:", r.status_code)

def fetch_stream_info(user_id):
    r = requests.get("https://api.twitch.tv/helix/streams", headers=HEADERS, params={"user_id": user_id})
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        return None
    s = data[0]
    title = s.get("title")
    game_id = s.get("game_id")
    game_name = None
    if game_id:
        gr = requests.get("https://api.twitch.tv/helix/games", headers=HEADERS, params={"id": game_id})
        gr.raise_for_status()
        gdata = gr.json().get("data", [])
        if gdata:
            game_name = gdata[0].get("name")
    return {"title": title, "game": game_name}

def verify_signature(request: Request, body: bytes):
    try:
        msg_id = request.headers["Twitch-Eventsub-Message-Id"]
        timestamp = request.headers["Twitch-Eventsub-Message-Timestamp"]
        signature = request.headers["Twitch-Eventsub-Message-Signature"]
    except KeyError:
        return False
    hmac_message = (msg_id + timestamp).encode() + body
    computed = "sha256=" + hmac.new(SECRET, hmac_message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)

@app.post("/twitch/callback")
async def twitch_callback(request: Request):
    body = await request.body()
    # Accept only verified Twitch signatures (protects endpoint)
    if not verify_signature(request, body):
        return {"status": "unauthorized"}

    data = await request.json()
    msg_type = request.headers.get("Twitch-Eventsub-Message-Type", "")

    # Respond to verification challenge
    if msg_type == "webhook_callback_verification":
        return data.get("challenge", "")

    # Normal notifications
    sub_type = data.get("subscription", {}).get("type", "")
    if sub_type == "stream.online":
        ev = data.get("event", {})
        broadcaster_id = ev.get("broadcaster_user_id")
        broadcaster_name = ev.get("broadcaster_user_name") or ev.get("broadcaster_user_login")
        # enrich with title/game using Helix
        info = fetch_stream_info(broadcaster_id) or {}
        title = info.get("title") or "No title"
        game = info.get("game") or ""
        url = f"https://twitch.tv/{ev.get('broadcaster_user_login') or broadcaster_name}"
        # Minimal Discord notification
        content = f"🔴 {broadcaster_name} is live!\n{title}{(' — ' + game) if game else ''}\n{url}"
        # send to Discord webhook
        requests.post(DISCORD_WEBHOOK, json={"content": content})
        print(content)

    return {"status": "ok"}

if __name__ == "__main__":
    # subscribe to each user listed in twitch_users.txt
    try:
        with open("twitch_users.txt", "r", encoding="utf-8") as f:
            for raw in f:
                login = raw.strip()
                if not login:
                    continue
                try:
                    uid, display, login_clean = get_user_id(login)
                    subscribe_stream_online(uid)
                    print(f"Subscribed to {display} ({login_clean}) -> {uid}")
                except Exception as e:
                    print(f"Skipping {login}: {e}")
    except FileNotFoundError:
        print("twitch_users.txt not found. Create it with one twitch username per line.")

    uvicorn.run(app, host="0.0.0.0", port=8000)
