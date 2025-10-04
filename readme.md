1) venv
2) pip install -r requirements.txt
3) Fill the following:
```
Twitch app credentials (make a Twitch dev app)
CLIENT_ID = "your_twitch_client_id"
CLIENT_SECRET = "your_twitch_client_secret"

Discord webhook URL (channel you want to notify)
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/.../... "

Secret used to validate Twitch signatures
SECRET = b"supersecret"

CALLBACK_URL = "https://yourdomain.com/twitch/callback"

```

4) run bot.py
5) success? idk, Perchi lmk.