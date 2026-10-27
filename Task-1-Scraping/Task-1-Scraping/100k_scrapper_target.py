import csv
import hashlib
import logging
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import requests
import feedparser
from bs4 import BeautifulSoup


# ================= SETTINGS =================

BASE = Path.home() / "Documents" / "Output"
BASE.mkdir(parents=True, exist_ok=True)

DB_PATH = BASE / "news_collector.sqlite3"
CSV_PATH = BASE / "articles_playwright_hybrid_dataset.csv"
SUMMARY_PATH = BASE / "source_summary.csv"
FAILED_PATH = BASE / "failed_sources.csv"

TARGET = 100_000
WORKERS = 8
TIMEOUT = 25
RETRIES = 2
CHECKPOINT = 20

COLS = [
    "article_id", "source", "title", "description", "author",
    "url", "published_at", "timezone", "scraped_at"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
}

logging.basicConfig(
    filename=str(BASE / "news_collector_fixed.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


# ================= ORIGINAL DIRECT SOURCES =================

SOURCES = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Top Stories", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("BBC Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ("Guardian World", "https://www.theguardian.com/world/rss"),
    ("Guardian UK", "https://www.theguardian.com/uk/rss"),
    ("Guardian Technology", "https://www.theguardian.com/technology/rss"),
    ("Guardian Business", "https://www.theguardian.com/business/rss"),
    ("Guardian Science", "https://www.theguardian.com/science/rss"),
    ("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("NYT Technology", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),
    ("NYT Business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ("NYT Science", "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml"),
    ("NYT Health", "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml"),
    ("NPR News", "https://feeds.npr.org/1001/rss.xml"),
    ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
    ("NPR Technology", "https://feeds.npr.org/1019/rss.xml"),
    ("Sky News World", "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("Sky News Technology", "https://feeds.skynews.com/feeds/rss/technology.xml"),
    ("Deutsche Welle", "https://rss.dw.com/rdf/rss-en-all"),
    ("France 24", "https://www.france24.com/en/rss"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Euronews", "https://www.euronews.com/rss"),
    ("The Hindu", "https://www.thehindu.com/news/international/feeder/default.rss"),
    ("Indian Express", "https://indianexpress.com/section/world/feed/"),
    ("Dawn", "https://www.dawn.com/feeds/home"),
    ("Japan Times", "https://www.japantimes.co.jp/feed/"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-topstories"),
    ("CBS News", "https://www.cbsnews.com/latest/rss/main"),
    ("USA Today", "https://rssfeeds.usatoday.com/usatoday-NewsTopStories"),
    ("Politico", "https://rss.politico.com/politics-news.xml"),
    ("The Hill", "https://thehill.com/feed/"),
    ("ABC News", "https://abcnews.go.com/abcnews/topstories"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Wired", "https://www.wired.com/feed/rss"),
    ("Engadget", "https://www.engadget.com/rss.xml"),
    ("ScienceDaily", "https://www.sciencedaily.com/rss/all.xml"),
    ("Phys.org", "https://phys.org/rss-feed/"),
    ("Medical Xpress", "https://medicalxpress.com/rss-feed/"),
    ("Financial Times", "https://www.ft.com/rss/home/international"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("The Register", "https://www.theregister.com/headlines.atom"),
    ("Fox News Latest", "https://moxie.foxnews.com/google-publisher/latest.xml"),
    ("Fox News Politics", "https://moxie.foxnews.com/google-publisher/politics.xml"),
    ("NBC News", "https://feeds.nbcnews.com/nbcnews/public/news"),
    ("AP via Flipboard", "https://flipboard.com/@associatedpress/top-stories-u7govdf1z.rss"),
    ("Hacker News", "https://news.ycombinator.com/rss"),
]

PUBLISHERS = [
    ("BBC", "bbc.co.uk"),
    ("The Guardian", "theguardian.com"),
    ("New York Times", "nytimes.com"),
    ("NPR", "npr.org"),
    ("Sky News", "news.sky.com"),
    ("DW", "dw.com"),
    ("France 24", "france24.com"),
    ("Al Jazeera", "aljazeera.com"),
    ("CBC", "cbc.ca"),
    ("The Hindu", "thehindu.com"),
    ("Indian Express", "indianexpress.com"),
    ("Dawn", "dawn.com"),
    ("Japan Times", "japantimes.co.jp"),
    ("CBS News", "cbsnews.com"),
    ("ABC News", "abcnews.go.com"),
    ("NBC News", "nbcnews.com"),
    ("Politico", "politico.com"),
    ("The Hill", "thehill.com"),
    ("TechCrunch", "techcrunch.com"),
    ("Wired", "wired.com"),
]

TOPICS = [
    "world news",
    "politics",
    "business",
    "technology",
    "science",
    "health",
    "climate",
    "education",
    "cybersecurity",
    "economy",
]


# ================= LOGGING / BACKUPS =================

def now_utc():
    return datetime.now(timezone.utc).isoformat()


def backup_file(path):
    if not path.exists():
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(
        f"{path.stem}_backup_{stamp}{path.suffix}"
    )

    with path.open("rb") as src, backup.open("wb") as dst:
        while True:
            block = src.read(1024 * 1024)
            if not block:
                break
            dst.write(block)

    print(f"File backup created: {backup}")


def backup_database():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}. "
            "Please check your Output folder."
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BASE / f"news_collector_backup_{stamp}.sqlite3"

    with sqlite3.connect(str(DB_PATH)) as source:
        with sqlite3.connect(str(backup)) as destination:
            source.backup(destination)

    print(f"Database backup created: {backup}")


# ================= DATABASE =================

def open_database():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}. "
            "Stopping to avoid creating an empty replacement database."
        )

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")

    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    if "articles" not in tables:
        conn.close()
        raise RuntimeError("Original articles table not found.")

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(articles)")
    }

    if not set(COLS).issubset(columns):
        conn.close()
        raise RuntimeError(
            "Original database columns do not match expected columns. "
            "No collection was started."
        )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS feed_status_fixed (
            feed_url TEXT PRIMARY KEY,
            feed_name TEXT,
            checked_at TEXT,
            article_count INTEGER DEFAULT 0,
            status TEXT,
            error TEXT
        )
    """)
    conn.commit()
    return conn


def total_articles(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM articles"
    ).fetchone()[0]


# ================= SEARCH GENERATION =================

def google_rss(query):
    params = {
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    return (
        "https://news.google.com/rss/search?"
        + urlencode(params)
    )


def monthly_windows(months):
    today = date.today()
    first = date(today.year, today.month, 1)
    result = []

    for offset in range(months):
        index = first.year * 12 + first.month - 1 - offset
        year, month0 = divmod(index, 12)
        start = date(year, month0 + 1, 1)

        next_index = index + 1
        next_year, next_month0 = divmod(next_index, 12)
        end = date(next_year, next_month0 + 1, 1)

        result.append((start.isoformat(), end.isoformat()))

    return result


def build_feeds():
    feeds = []
    seen = set()

    def add(name, url):
        if url not in seen:
            seen.add(url)
            feeds.append((name, url))

    for name, url in SOURCES:
        add(name, url)

    # 20 publishers x 10 topics = up to 200 current searches.
    for publisher, domain in PUBLISHERS:
        for topic in TOPICS:
            add(
                f"Current | {publisher} | {topic}",
                google_rss(f"site:{domain} {topic}")
            )

    # Historical searches, divided into monthly windows.
    for topic in TOPICS:
        for start, end in monthly_windows(60):
            add(
                f"Topic history | {topic} | {start}",
                google_rss(
                    f'{topic} after:{start} before:{end}'
                )
            )

    for publisher, domain in PUBLISHERS:
        for start, end in monthly_windows(24):
            add(
                f"Publisher history | {publisher} | {start}",
                google_rss(
                    f'site:{domain} after:{start} before:{end}'
                )
            )

    return feeds


# ================= FETCHING =================

def text_only(value):
    if not value:
        return ""
    return BeautifulSoup(
        str(value), "html.parser"
    ).get_text(" ", strip=True)


def normalize_url(url):
    try:
        parts = urlsplit(str(url).strip())
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
            return ""

        ignored = {
            "utm_source", "utm_medium", "utm_campaign",
            "utm_term", "utm_content", "fbclid", "gclid",
            "mc_cid", "mc_eid",
        }

        query = [
            (key, value)
            for key, value in parse_qsl(
                parts.query, keep_blank_values=True
            )
            if key.lower() not in ignored
        ]

        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(query, doseq=True),
            "",
        ))
    except (ValueError, TypeError):
        return ""


def published_date(entry):
    parsed = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
    )

    if parsed:
        try:
            return datetime(
                *parsed[:6], tzinfo=timezone.utc
            ).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass

    return str(
        entry.get("published")
        or entry.get("updated")
        or ""
    ).strip()


def fetch_feed(feed):
    name, feed_url = feed
    last_error = ""

    for attempt in range(RETRIES + 1):
        try:
            response = requests.get(
                feed_url,
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            response.raise_for_status()

            parsed = feedparser.parse(response.content)
            rows = []

            for entry in parsed.entries:
                title = text_only(
                    entry.get("title", "")
                ).strip()
                url = normalize_url(entry.get("link", ""))

                if not title or not url:
                    continue

                # URL-based IDs avoid collisions between different
                # articles that happen to have the same title.
                article_id = hashlib.sha256(
                    url.encode("utf-8")
                ).hexdigest()

                rows.append({
                    "article_id": article_id,
                    "source": name,
                    "title": title,
                    "description": text_only(
                        entry.get("summary", "")
                        or entry.get("description", "")
                    ),
                    "author": text_only(
                        entry.get("author", "")
                    ),
                    "url": url,
                    "published_at": published_date(entry),
                    "timezone": "UTC",
                    "scraped_at": now_utc(),
                })

            return {
                "name": name,
                "url": feed_url,
                "rows": rows,
                "count": len(rows),
                "status": "ok" if rows else "empty",
                "error": "",
            }

        except Exception as exc:
            last_error = str(exc)
            logging.warning("%s failed: %s", name, last_error)

            if attempt < RETRIES:
                time.sleep(attempt + 1)

    return {
        "name": name,
        "url": feed_url,
        "rows": [],
        "count": 0,
        "status": "failed",
        "error": last_error,
    }


# ================= SAVING =================

def save_result(conn, result, allow_articles=True):
    conn.execute("""
        INSERT INTO feed_status_fixed
        (feed_url, feed_name, checked_at, article_count, status, error)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(feed_url) DO UPDATE SET
            feed_name=excluded.feed_name,
            checked_at=excluded.checked_at,
            article_count=excluded.article_count,
            status=excluded.status,
            error=excluded.error
    """, (
        result["url"],
        result["name"],
        now_utc(),
        result["count"],
        result["status"],
        result["error"],
    ))

    inserted = 0

    if allow_articles:
        for row in result["rows"]:
            if total_articles(conn) >= TARGET:
                break

            before = conn.total_changes

            conn.execute("""
                INSERT OR IGNORE INTO articles
                (article_id, source, title, description, author,
                 url, published_at, timezone, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(row[column] for column in COLS))

            if conn.total_changes > before:
                inserted += 1

    return inserted


def export_csv(conn):
    temp = CSV_PATH.with_name(CSV_PATH.name + ".tmp")

    with temp.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(COLS)

        cursor = conn.execute("""
            SELECT article_id, source, title, description, author,
                   url, published_at, timezone, scraped_at
            FROM articles
            ORDER BY scraped_at DESC
        """)

        while True:
            batch = cursor.fetchmany(2000)
            if not batch:
                break
            writer.writerows(batch)

    temp.replace(CSV_PATH)


def export_reports(conn):
    with SUMMARY_PATH.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file)
        writer.writerow([
            "feed_name", "feed_url", "checked_at",
            "article_count", "status", "error"
        ])
        writer.writerows(conn.execute("""
            SELECT feed_name, feed_url, checked_at,
                   article_count, status, error
            FROM feed_status_fixed
            ORDER BY feed_name
        """))

    with FAILED_PATH.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["feed_name", "feed_url", "error"])
        writer.writerows(conn.execute("""
            SELECT feed_name, feed_url, error
            FROM feed_status_fixed
            WHERE status IN ('failed', 'empty')
            ORDER BY feed_name
        """))


# ================= MAIN =================

def main():
    print("=" * 65)
    print("NEWS COLLECTOR - RESUME EXISTING DATABASE")
    print("=" * 65)

    # Check the existing database before starting.
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database missing: {DB_PATH}. Stopping safely."
        )

    # Make backups before modifying the database or CSV.
    backup_database()
    backup_file(CSV_PATH)

    conn = open_database()

    try:
        starting = total_articles(conn)
        print(f"Existing database articles: {starting:,}")

        if starting >= TARGET:
            print("Target already reached.")
            export_csv(conn)
            export_reports(conn)
            return

        feeds = build_feeds()

        print(f"Direct RSS feeds: {len(SOURCES)}")
        print(f"Publisher domains: {len(PUBLISHERS)}")
        print(f"Topics: {len(TOPICS)}")
        print(f"Total distinct feeds/searches: {len(feeds):,}")
        print(f"Target: {TARGET:,}")
        print(f"Output folder: {BASE}")
        print("Collection started. Keep this terminal open.")
        print("-" * 65)

        inserted_total = 0
        completed = 0

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {
                pool.submit(fetch_feed, feed): feed
                for feed in feeds
            }

            for future in as_completed(futures):
                result = future.result()

                inserted_total += save_result(
                    conn,
                    result,
                    allow_articles=(total_articles(conn) < TARGET),
                )
                completed += 1

                if completed % CHECKPOINT == 0:
                    conn.commit()
                    export_csv(conn)
                    export_reports(conn)

                    current = total_articles(conn)
                    print(
                        f"[{completed}/{len(feeds)}] "
                        f"Articles: {current:,} | "
                        f"New this run: {inserted_total:,}"
                    )

                if total_articles(conn) >= TARGET:
                    print("Target reached. Finishing safely.")
                    break

        conn.commit()
        export_csv(conn)
        export_reports(conn)

        final_count = total_articles(conn)

        print("\n" + "=" * 65)
        print("COLLECTION FINISHED")
        print(f"Before run: {starting:,}")
        print(f"New unique articles: {inserted_total:,}")
        print(f"Total database articles: {final_count:,}")
        print(f"CSV: {CSV_PATH}")
        print(f"Summary: {SUMMARY_PATH}")
        print(f"Failed sources report: {FAILED_PATH}")
        print("=" * 65)

        if final_count < TARGET:
            print(
                "The target was not reached this run. "
                "RSS search results are limited and do not guarantee "
                "100,000 articles."
            )
        else:
            print("Target of 100,000 articles reached.")

    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user. Saved database records are preserved.")
    except Exception as exc:
        logging.exception("Collector stopped")
        print(f"\nERROR: {exc}")
        print("Check the output above. Do not delete your database.")