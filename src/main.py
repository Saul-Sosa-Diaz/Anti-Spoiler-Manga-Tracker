import json
import logging
import os
import re
import time
import urllib.parse
import unicodedata
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

DISCORD_MENTION = os.getenv("DISCORD_MENTION", "")
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
            "japones",
            "filtración",
            "próximamente",
            "fecha de estreno",
        }
        self.pending_or_untranslated_keywords = {
            "sin traducir",
            "traduccion pendiente",
            "traduccion parcial",
            "en proceso",
            "pendiente",
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFD", text.lower())
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    @staticmethod
    def _to_word_text(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text).strip()

    def _matches_manga_name(self, candidate_text: str, manga_name: str) -> bool:
        candidate_words = self._to_word_text(candidate_text)
        manga_tokens = [t for t in self._to_word_text(manga_name).split() if t]
        if not manga_tokens:
            return False
        return all(token in candidate_words for token in manga_tokens)

    def send_notification(self, manga_name: str, chapter: int, url: str) -> bool:
        if not self.webhook_url:
            return False

        manga_title = manga_name.title()

        # Prepare the message content, prefixing with a mention if configured
        message_content = f"Capítulo {chapter} de **{manga_title}** YA ESTÁ DISPONIBLE en español y sin spoilers. {url}"
        if DISCORD_MENTION:
            message_content = f"{DISCORD_MENTION} {message_content}"

        payload = {
            "content": message_content,
            "username": f"Radar {manga_title}",
            "avatar_url": "https://static.wikia.nocookie.net/49d3ad00-c253-4f2a-bfdb-457851c80aa2/scale-to-width/755",
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except requests.RequestException:
            return False

    def _chapter_page_is_valid(
        self, chapter_url: str, manga_name: str, chapter_number: int
    ) -> Tuple[bool, Optional[str]]:
        """Validates a candidate chapter page before sending notifications."""
        normalized_manga = self._normalize_text(manga_name)
        chapter_regex = re.compile(rf"\b{re.escape(str(chapter_number))}\b")
        normalized_forbidden = {
            self._normalize_text(w) for w in self.forbidden_keywords
        }
        normalized_pending = {
            self._normalize_text(w) for w in self.pending_or_untranslated_keywords
        }

        try:
            response = requests.get(chapter_url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                return (False, f"Chapter page HTTP {response.status_code}")

            soup = BeautifulSoup(response.text, "html.parser")
            article = (
                soup.find(class_="post-body")
                or soup.find("article")
                or soup.find("body")
            )
            if not article:
                return (False, "Chapter page has no content body")

            for tag in article.find_all(["script", "style", "noscript"]):
                tag.decompose()

            page_title = ""
            if soup.title and soup.title.string:
                page_title = soup.title.string
            heading = soup.find("h1")
            heading_text = heading.get_text(" ", strip=True) if heading else ""

            visible_content = article.get_text(" ", strip=True)
            combined_text = self._normalize_text(
                " ".join([page_title, heading_text, visible_content])
            )

            if not self._matches_manga_name(combined_text, normalized_manga):
                return (False, "Manga name not found on chapter page")
            if not chapter_regex.search(combined_text):
                return (False, "Chapter number not found on chapter page")

            if any(word in combined_text for word in normalized_pending):
                return (False, "Chapter appears pending/unfinished")
            if any(word in combined_text for word in normalized_forbidden):
                return (False, "Chapter page contains forbidden markers")

            image_urls = []
            for img in article.find_all("img"):
                src = img.get("src") or img.get("data-src")
                if src:
                    image_urls.append(src)

            if len(image_urls) < 5:
                return (False, "Chapter page has too few manga images")

            return (True, None)

        except requests.RequestException as error:
            return (False, f"Chapter page request failed: {error}")

    def scan_chapter(
        self, manga_name: str, chapter_number: int
    ) -> Tuple[str, Optional[str], str]:
        """Returns (status, error_detail, url) where url is the matching chapter URL if found."""
        query = urllib.parse.quote_plus(f"{manga_name} manga {chapter_number}")
        search_url = f"https://www.animeallstar1.com/search?q={query}"
        normalized_manga = self._normalize_text(manga_name)
        normalized_forbidden = {
            self._normalize_text(w) for w in self.forbidden_keywords
        }
        chapter_regex = re.compile(rf"\b{re.escape(str(chapter_number))}\b")

        try:
            response = requests.get(search_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                return ("not_found", f"HTTP {response.status_code}", search_url)

            soup = BeautifulSoup(response.text, "html.parser")
            article = soup.find("body") or soup

            if not article:
                return ("not_found", "No article body found", search_url)

            # Evaluate individual result links so a single "raw/spoiler" post
            # does not invalidate the whole search page.
            found_but_forbidden = False
            last_candidate_rejection_detail: Optional[str] = None
            for link in article.select("a[href]"):
                href = link.get("href", "")
                if not href:
                    continue

                link_text = link.get_text(" ", strip=True)
                image = link.find("img")
                image_alt = image.get("alt", "") if image else ""
                link_title = link.get("title", "")

                combined_text = " ".join(
                    part for part in [link_text, image_alt, link_title, href] if part
                )
                normalized_combined = self._normalize_text(combined_text)

                if not self._matches_manga_name(normalized_combined, normalized_manga):
                    continue
                if not chapter_regex.search(normalized_combined):
                    continue

                if any(word in normalized_combined for word in normalized_forbidden):
                    found_but_forbidden = True
                    last_candidate_rejection_detail = (
                        "Search result contains forbidden markers (raw/spoiler)."
                    )
                    continue

                if "espanol" in normalized_combined:
                    candidate_url = urllib.parse.urljoin(search_url, href)
                    is_valid, validation_detail = self._chapter_page_is_valid(
                        candidate_url, manga_name, chapter_number
                    )
                    if is_valid:
                        return ("found", None, candidate_url)

                    last_candidate_rejection_detail = (
                        validation_detail
                        or "Candidate chapter page did not pass validation"
                    )
                    normalized_validation = self._normalize_text(
                        last_candidate_rejection_detail
                    )
                    if any(
                        marker in normalized_validation
                        for marker in ["forbidden", "raw", "spoiler", "pending"]
                    ):
                        found_but_forbidden = True
                    continue

            if found_but_forbidden:
                return (
                    "forbidden_keyword_detected",
                    last_candidate_rejection_detail
                    or "Only spoiler/raw results matched chapter",
                    search_url,
                )

            if last_candidate_rejection_detail:
                return (
                    "not_found",
                    f"Candidate rejected: {last_candidate_rejection_detail}",
                    search_url,
                )

            return (
                "not_found",
                "Placeholder detected (missing images or Spanish confirmation)",
                search_url,
            )

        except requests.RequestException as error:
            return ("error", str(error), search_url)


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
            status, detail, chapter_url = tracker.scan_chapter(
                manga_name, current_chapter
            )
            canonical_log["scan_status"] = status
            if detail:
                canonical_log["error_detail"] = detail

            if status == "found":
                notified = tracker.send_notification(
                    manga_name, current_chapter, chapter_url
                )
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
