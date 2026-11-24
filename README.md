# Apple UAE iPhone Duo Stock Monitor

A Python automation project that monitors Apple's UAE in-store pickup availability for the iPhone Duo (256GB) and sends Telegram alerts when stock becomes available at selected Apple Stores in Abu Dhabi and Dubai.

**Repository:** [LevonGrig/IphoneDuoChecker](https://github.com/LevonGrig/IphoneDuoChecker)

## Project overview

This project demonstrates a practical automation workflow: poll a third-party availability source, normalize the response, persist state, detect changes, and notify a user through Telegram.

### Monitored configurations

| Model | Storage | Colour | Apple part number |
|---|---:|---|---|
| iPhone Duo | 256GB | Star White | `MK244AH/A` |
| iPhone Duo | 256GB | Night Sky | `MK254AH/A` |

### Monitored stores

| Apple Store | City | Store ID |
|---|---|---|
| Al Maryah Island | Abu Dhabi | `R706` |
| Yas Mall | Abu Dhabi | `R595` |
| Dubai Mall | Dubai | `R597` |
| Mall of the Emirates | Dubai | `R596` |

The monitor checks the two city pickup searches and evaluates the selected store/colour combinations approximately every 60 seconds by default.

## Features

- **Apple pickup monitoring:** requests Apple's UAE pickup availability response for both product configurations.
- **Change detection:** sends an alert when a configuration is first confirmed available or transitions from unavailable to available.
- **Telegram commands:** `/status`, `/history`, `/ping`, and `/help`.
- **SQLite persistence:** saves current stock state, transition history, pending notifications, and Telegram polling offset.
- **Notification retry:** keeps restock alerts pending if Telegram temporarily fails, then retries them.
- **Conservative parsing:** unknown or missing product/store data does not get interpreted as out of stock.
- **Cloud-ready:** designed to run as one persistent worker with a mounted data volume.

## Architecture

```text
Apple UAE pickup endpoint
          |
          v
  Python async monitor
          |
          v
  Availability parser
          |
          v
  Stock state / transitions -----> SQLite database
          |
          v
  Telegram notification worker
          |
          v
  Personal Telegram chat

Telegram commands -----> Telegram polling -----> /status, /history, /ping, /help
```

## Technology stack

- Python 3.11+
- `httpx` for asynchronous HTTP requests
- Telegram Bot API for alerts and commands
- SQLite for persistent state and event history
- `python-dotenv` for local environment configuration
- Railway for optional always-on cloud hosting

## Run locally

### 1. Clone the repository

```bash
git clone https://github.com/LevonGrig/IphoneDuoChecker.git
cd IphoneDuoChecker
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example file:

```bash
cp .env.example .env
```

Set your own values in `.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_private_chat_id
CHECK_INTERVAL=60
DATA_DIR=data
```

Never commit `.env` or share your Telegram bot token. The real `.env` file is excluded by `.gitignore`.

### 4. Start the monitor

```bash
python main.py
```

The bot sends a startup notification and begins monitoring. Use the following commands in your private Telegram chat:

| Command | Description |
|---|---|
| `/status` | Current status for all monitored store/colour combinations |
| `/history` | Recent availability and sold-out events |
| `/ping` | Confirm that the bot is responding |
| `/help` | Show available commands |

## Tests

Run the automated tests with:

```bash
python -m unittest discover -s tests -v
```

The tests cover availability response parsing, unknown-status handling, and stock-transition history.

## Deploy to Railway

This application is a long-running worker, not a web server or scheduled job.

1. Create a Railway project and deploy from this public GitHub repository.
2. Set the start command to `python main.py`.
3. Add these service variables:
   - `TELEGRAM_BOT_TOKEN`: your newly generated BotFather token
   - `TELEGRAM_CHAT_ID`: your private Telegram chat ID
   - `CHECK_INTERVAL`: `60`
   - `DATA_DIR`: `/app/data`
4. Attach a Railway Volume mounted at `/app/data` to preserve the SQLite database across deployments.
5. Run **one replica only** to avoid duplicate Apple polling and competing Telegram long-polling clients.
6. Check deployment logs and send `/status` to the bot after it starts.

## Important limitations

- Apple's pickup endpoint is an undocumented endpoint used by its shopping website, not a supported public API. Apple may change its response format, availability fields, or access controls.
- Availability is only a point-in-time observation. Stock can disappear before checkout; an alert is not a reservation.
- The normal polling interval is 60 seconds by default. Repeated HTTP 541 responses trigger an automatic cooldown that grows from 15 to 30 to 60 minutes after consecutive blocks. During a 541 cooldown, the normal 60-second interval is suspended until the next retry. Do not try to bypass Apple's access controls or keep retrying during a block.
- A missing store, missing part, malformed response, or unknown pickup status must be treated as unknown rather than unavailable.

## Security

- Keep the repository free of real bot tokens, chat credentials, and database files.
- Store local credentials in `.env`; store cloud credentials in Railway service variables.
- If a Telegram bot token is exposed in a terminal log, screenshot, chat, or commit, revoke it with BotFather and generate a replacement.

---

Built as a hands-on Python automation and API-integration portfolio project.
