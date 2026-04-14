# Anti-Spoiler Manga Tracker

## Project Motivation
This project was developed out of the frustration of constantly encountering manga spoilers, leaks, and raw scans on social media while waiting for new chapter releases. I was tired of having the experience ruined, so I created this automated script to safely track releases without exposing myself to spoilers.

The bot silently monitors [AnimeAllStar1](https://www.animeallstar1.com) to check if the chapter is available **fully translated and without being a leak, raw, or text spoiler**. When the chapter is confirmed to be ready to read in good quality, it sends a notification directly to a configured Discord server.

## Features
- **Automated and silent:** No infinite loops. Runs exactly once per execution.
- **Anti-Fake Detector:** Ignores placeholder pages that only say "release date" or "spoilers/raws" without having the actual manga images.
- **Multi-Manga JSON Tracking:** Centrally track Multiple mangas and their current chapters using the versatile `mangas.json` database.
- **GitHub Actions Integration:** Avoid using your own hardware entirely. Native cron schedules run via GitHub Actions and automatically commit state updates back to your repository.
- **Canonical Logging:** Logs every scan cleanly (JSON format), perfect for ingesting into log management systems without cluttering your console.
- **Git Auto-Commit:** Can be configured to automatically `git commit` and `git push` the `mangas.json` file when a new chapter drops, ensuring your central repository stays updated. 

## Installation and Usage

1. **GitHub Setup (Recommended):**
   - Fork or clone this repository.
   - Go to your repository's **Settings > Secrets and variables > Actions**.
   - Add a new repository secret called `DISCORD_WEBHOOK_URL` containing your Discord webhook.
   - Adjust `mangas.json` in your code with the names of the mangas and the chapters you are waiting for. Commits back to the file will happen automatically!

2. **Local execution (Optional):**
   ```bash
   pip install -r requirements.txt
   cp .env.example .env
   # Add your webhook into the .env file
   python3 src/main.py
   ```

   **Local Automation (Cron):**
   If you run this on a home server (like a Raspberry Pi), open your crontab (`crontab -e`) and configure it to run mechanically on Thursdays and Fridays:
   ```cron
   # Thursday: Run every hour from 12:00 PM to 11:00 PM (Without auto-push)
   0 12-23 * * 4 cd /path/to/one-piece-tracker && /usr/bin/python3 src/main.py >> logs/scan.log 2>&1

   # Friday: Run every hour all day (Without auto-push)
   0 * * * 5 cd /path/to/one-piece-tracker && /usr/bin/python3 src/main.py >> logs/scan.log 2>&1
   
   # --- ALTERNATIVE WITH GIT AUTO-PUSH ---
   # NOTE: This script (`track-and-push.sh`) is designed mainly for me to keep the main repository up to date automatically when new chapters are out.
   # For your personal forks or clones, you should just run `python3 src/main.py` directly as shown above to avoid unsolicited pushes to your repository.
   # 0 12-23 * * 4 cd /path/to/one-piece-tracker && ./track-and-push.sh >> logs/scan.log 2>&1
   # 0 * * * 5 cd /path/to/one-piece-tracker && ./track-and-push.sh >> logs/scan.log 2>&1
   ```

## Configuration
All manga targets and their current expectation states are stored in `mangas.json`:

```json
{
  "mangas": [
    {
      "name": "one piece",
      "current_chapter": 1179
    },
    {
      "name": "jujutsu kaisen",
      "current_chapter": 260
    }
  ]
}
```

Whenever the bot detects a chapter reliably, it notifies Discord and increases `current_chapter` locally. If running via GitHub Actions, the bot automatically commits and pushes the new number to your codebase.

Enjoy your manga without stress or spoilers!
