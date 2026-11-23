
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

if not token or not chat_id:
    raise ValueError("Missing Telegram configuration in .env")

url = f"https://api.telegram.org/bot{token}/sendMessage"

response = httpx.post(
    url,
    json={
        "chat_id": chat_id,
        "text": (
            "✅ Apple UAE Stock Monitor connected!\n\n"
            "📱 iPhone Duo 256GB\n"
            "🎨 Star White + Night Sky\n"
            "📍 Abu Dhabi + Dubai\n"
            "⏱ Monitoring interval: 30 seconds"
        )
    },
    timeout=20
)

response.raise_for_status()

result = response.json()

if not result.get("ok"):
    raise RuntimeError(result)

print("Telegram notification sent successfully!")
