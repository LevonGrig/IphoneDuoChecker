import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATABASE_PATH = DATA_DIR / "apple_stock.sqlite3"

APPLE_PICKUP_URL = "https://www.apple.com/ae/shop/retail/pickup-message"
APPLE_PRODUCT_URL = "https://www.apple.com/ae/shop/buy-iphone/iphone-duo"
APPLE_SEARCH_LOCATION = "Abu Dhabi"

if CHECK_INTERVAL < 30:
    raise ValueError("CHECK_INTERVAL must be at least 30 seconds")


def validate_config() -> None:
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is missing from .env / environment")
    if not CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID is missing from .env / environment")

STORES = {
    "R706": {"name": "Al Maryah Island", "city": "Abu Dhabi"},
    "R595": {"name": "Yas Mall", "city": "Abu Dhabi"},
    "R597": {"name": "Dubai Mall", "city": "Dubai"},
    "R596": {"name": "Mall of the Emirates", "city": "Dubai"},
}

PRODUCTS = {
    "MK244AH/A": {"name": "iPhone Duo 256GB Star White", "colour": "Star White"},
    "MK254AH/A": {"name": "iPhone Duo 256GB Night Sky", "colour": "Night Sky"},
}
