import os
import hmac
import hashlib
import json
import aiohttp
from fastapi import FastAPI, Request
import uvicorn

# Twitch API credentials
CLIENT_ID = "your_client_id"
APP_TOKEN = "your_app_access_token"  # Use a valid App Access Token
SECRET = b"supersecret"  # Must match what you use in Twitch webhook setup
CALLBACK_URL = "https://twitch.domain.me/twitch/callback"

# Discord Webhook
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your_webhook_id/your_token"

app = FastAPI()

# -------------------------------------------------------------------
# Read user IDs from text file
# -------------------------------------------------------------------
def read_user_ids(filename="streamers.txt"):
    ids = []
    with open(filename, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped.isdigit():
                ids.append(stripped)
    return ids


# -------------------------------------------------------------------
# Subscribe each user ID to Twitch EventSub "stream.online"
# -------------------------------------------------------------------
async def subscribe_to_user(session, user_id):
    url = "https://api.twitch.tv/helix/eventsub/subscriptions"
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {APP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": "stream.online",
        "version": "1",
        "condition": {"broadcaster_user_id": user_id},
        "transport": {
            "method": "webhook",
            "callback": CALLBACK_URL,
            "secret": SECRET.decode(),
        },
    }

    async with session.post(url, headers=headers, json=payload) as resp:
        text = await resp.text()
        print(f"Subscribed to {user_id}:", resp.status, text)


# -------------------------------------------------------------------
# Verify Twitch signature
# -------------------------------------------------------------------
def verify_twitch_signature(request: Request, body: bytes):
    msg_id = request.headers.get("Twitch-Eventsub-Message-Id", "")
    timestamp = request.headers.get("Twitch-Eventsub-Message-Timestamp", "")
    msg_signature = request.headers.get("Twitch-Eventsub-Message-Signature", "")

    hmac_message = msg_id.encode() + timestamp.encode() + body
    expected = "sha256=" + hmac.new(SECRET, hmac_message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, msg_signature)


# -------------------------------------------------------------------
# Twitch callback handler
# -------------------------------------------------------------------
@app.post("/twitch/callback")
async def twitch_callback(request: Request):
    body = await request.body()

    if not verify_twitch_signature(request, body):
        return {"error": "invalid signature"}

    data = json.loads(body)
    msg_type = request.headers.get("Twitch-Eventsub-Message-Type")

    # Verification challenge
    if msg_type == "webhook_callback_verification":
        print("Twitch verification request received")
        return data["challenge"]

    # Stream Online event
    if msg_type == "notification" and data["subscription"]["type"] == "stream.online":
        event = data["event"]
        broadcaster = event["broadcaster_user_login"]

        async with aiohttp.ClientSession() as session:
            await session.post(DISCORD_WEBHOOK_URL, json={
                "content": f"🔴 {broadcaster} is now LIVE on Twitch! https://twitch.tv/{broadcaster}"
            })
        print(f"Sent Discord message for {broadcaster}")

    return {"ok": True}


# -------------------------------------------------------------------
# Startup — subscribe to all IDs in the file
# -------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    user_ids = read_user_ids()
    async with aiohttp.ClientSession() as session:
        for user_id in user_ids:
            await subscribe_to_user(session, user_id)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
