
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TELEGRAM_BOT_TOKEN")

if not token:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN in .env")

url = f"https://api.telegram.org/bot{token}/getUpdates"

response = httpx.get(url, timeout=20)
response.raise_for_status()

data = response.json()

if not data.get("ok"):
    raise RuntimeError(f"Telegram API error: {data}")

updates = data.get("result", [])

private_chats = [
    update["message"]["chat"]
    for update in updates
    if "message" in update
    and update["message"]["chat"].get("type") == "private"
]

if not private_chats:
    print("No messages found.")
    print("Open your bot in Telegram and send /start.")
else:
    chat = private_chats[-1]
    print("Telegram connection details:")
    print("Chat ID:", chat["id"])
    print("Username:", chat.get("username", "Not available"))
