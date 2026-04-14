import json
import logging
import os
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("Environment variable DISCORD_WEBHOOK_URL is not set.")

JSON_DB_FILE = "mangas.json"

# Configure logging to just output the raw message (which will be JSON)
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class MangaTracker:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        self.forbidden_keywords = {
            "spoiler",
            "spoilers",
            "raw",
            "japonés",
            "filtración",
            "próximamente",
            "fecha de estreno",
        }

    def send_notification(self, manga_name: str, chapter: int) -> bool:
        if not self.webhook_url:
            return False

        manga_title = manga_name.title()
        payload = {
            "content": f"Capítulo {chapter} de **{manga_title}** YA ESTÁ DISPONIBLE en español y sin spoilers.",
            "username": f"Radar {manga_title}",
            "avatar_url": "https://static.wikia.nocookie.net/49d3ad00-c253-4f2a-bfdb-457851c80aa2/scale-to-width/755",
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except requests.RequestException:
            return False

    def scan_chapter(
        self, manga_name: str, chapter_number: int
    ) -> Tuple[str, Optional[str]]:
        """Returns a tuple of (status: str, error_detail: Optional[str])."""
        query = urllib.parse.quote_plus(f"{manga_name} manga {chapter_number}")
        search_url = f"https://www.animeallstar1.com/search?q={query}"

        try:
            response = requests.get(search_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                return ("not_found", f"HTTP {response.status_code}")

            soup = BeautifulSoup(response.text, "html.parser")
            article = soup.find(class_="post-body") or soup.find("body")

            if not article:
                return ("not_found", "No article body found")

            content = article.text.lower()
            images = article.find_all("img")

            for word in self.forbidden_keywords:
                if word in content:
                    return ("forbidden_keyword_detected", word)

            if "español" in content and len(images) >= 5:
                return ("found", None)

            return (
                "not_found",
                "Placeholder detected (missing images or Spanish confirmation)",
            )

        except requests.RequestException as error:
            return ("error", str(error))


def main() -> None:
    if not os.path.exists(JSON_DB_FILE):
        logger.error(
            json.dumps({"error": f"Configuration file {JSON_DB_FILE} not found."})
        )
        return

    with open(JSON_DB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    tracker = MangaTracker(WEBHOOK_URL)
    changes_made = False

    for manga in data.get("mangas", []):
        start_time = time.time()
        manga_name = manga.get("name")
        current_chapter = manga.get("current_chapter")

        if not manga_name or not current_chapter:
            continue

        # Initialize the canonical log context for each manga
        canonical_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "manga_scan",
            "manga_name": manga_name,
            "chapter_checked": current_chapter,
            "scan_status": "started",
            "discord_notified": False,
            "error_detail": None,
            "duration_ms": 0,
        }

        try:
            status, detail = tracker.scan_chapter(manga_name, current_chapter)
            canonical_log["scan_status"] = status
            if detail:
                canonical_log["error_detail"] = detail

            if status == "found":
                notified = tracker.send_notification(manga_name, current_chapter)
                canonical_log["discord_notified"] = notified

                if notified:
                    manga["current_chapter"] += 1
                    changes_made = True

        except Exception as e:
            canonical_log["scan_status"] = "fatal_error"
            canonical_log["error_detail"] = str(e)

        finally:
            canonical_log["duration_ms"] = round((time.time() - start_time) * 1000, 2)
            logger.info(json.dumps(canonical_log))

    # If any chapter was incremented, persist changes to the JSON database
    if changes_made:
        with open(JSON_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
