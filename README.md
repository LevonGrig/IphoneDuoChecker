# Apple UAE iPhone Duo Stock Monitor

A small Python worker that checks Apple's UAE pickup JSON for iPhone Duo 256GB Star White and Night Sky at four selected Apple Stores and sends Telegram alerts when pickup changes to available.

## Monitored stores

- Apple Al Maryah Island, Abu Dhabi (`R706`)
- Apple Yas Mall, Abu Dhabi (`R595`)
- Apple Dubai Mall, Dubai (`R597`)
- Apple Mall of the Emirates, Dubai (`R596`)

## Local setup

1. Use Python 3.11 or newer.
2. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and enter the newly rotated Telegram token and your private chat ID.
4. Run the worker:

   ```bash
   python main.py
   ```

The worker polls Apple approximately every 30 seconds. Telegram commands are `/status`, `/history`, `/ping`, and `/help`.

## Stock-state behavior

- Only explicit Apple `pickupDisplay` values of `available` or `unavailable` update stock state.
- Unknown, malformed, or missing store/product data is not treated as out of stock.
- SQLite stores state and transition history.
- Pending restock notifications are retried if Telegram temporarily fails.
- The first confirmed available observation creates an alert, even if the bot has just started.

Apple's pickup endpoint is an undocumented website endpoint, not a supported public API. Apple can change its response format or limit automated traffic. Keep the polling interval at or above 30 seconds and use the result as an alert, not a reservation guarantee.

## Railway deployment

1. Push this project to a **private** GitHub repository. Do not commit `.env`, your bot token, or the SQLite database.
2. In Railway, create a project and choose **Deploy from GitHub Repo**. Connect the private repository.
3. In the service settings, set the Start Command to:

   ```bash
   python main.py
   ```

4. Add these service variables:

   - `TELEGRAM_BOT_TOKEN` = your newly rotated BotFather token
   - `TELEGRAM_CHAT_ID` = your private Telegram chat ID
   - `CHECK_INTERVAL` = `30`
   - `DATA_DIR` = `/app/data`

5. Add a Railway Volume and set its mount path to `/app/data`. This keeps the SQLite database across deployments.
6. Deploy. Check the service logs for `Monitor started` and the scan messages. Then send `/status` to your Telegram bot.

Use one running Railway replica only: two copies would poll Apple twice and compete for Telegram `getUpdates`.
