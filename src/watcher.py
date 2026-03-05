import os, re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from db import connect, init_db, is_seen, upsert_job
from telegram import send_message

load_dotenv()

WATCH_URL = os.getenv("WATCH_URL", "").strip()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
DB_PATH = os.getenv("DB_PATH", "data/jobs.sqlite3").strip()

if not WATCH_URL or not TOKEN or not CHAT_ID:
    raise SystemExit("Set WATCH_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID in .env")

# Front-end targeting (tweak freely)
INCLUDE = [
    "frontend", "front-end", "front end", "react", "javascript", "typescript", "ui engineer"
]
EXCLUDE = [
    "manager", "director", "intern", "qa", "recruiter", "sales"
]

def norm_url(base: str, href: str) -> str:
    u = urljoin(base, href)
    p = urlparse(u)
    return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))

def fetch(url: str) -> str:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,uk;q=0.8",
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    })
    r = s.get(url, timeout=30, allow_redirects=True)
    if r.status_code == 403:
        raise RuntimeError("403 Forbidden: Wellfound is blocking scripted requests for this page.")
    r.raise_for_status()
    return r.text

def looks_like_job_link(href: str) -> bool:
    # Heuristic; adjust after you see what the page returns
    return bool(re.search(r"/jobs?/|/role/|/company/|/startup/", href))

def title_matches(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in INCLUDE) and not any(x in t for x in EXCLUDE)

def extract_jobs_from_listing(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, str] = {}

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        title = a.get_text(" ", strip=True)

        if not title or len(title) < 4:
            continue
        if not looks_like_job_link(href):
            continue
        if not title_matches(title):
            continue

        url = norm_url(base_url, href)
        out[url] = title[:140]

    return [(title, url) for url, title in out.items()]

def enrich_from_job_page(job_url: str) -> tuple[str | None, str | None]:
    """
    Best-effort: HTML structures change. We try common patterns:
    - Open Graph site_name / title chunks
    - obvious 'Salary' text blocks
    If we fail, we return (None, None) and still store the job.
    """
    html = fetch(job_url)
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.stripped_strings)

    # Salary guess: look for currency patterns
    salary = None
    m = re.search(r"(\$|€|£)\s?\d[\d,]*(?:\s?-\s?(\$|€|£)\s?\d[\d,]*)?", text)
    if m:
        salary = m.group(0)

    # Company guess: try meta tags first
    company = None
    og_site = soup.select_one('meta[property="og:site_name"]')
    if og_site and og_site.get("content"):
        company = og_site["content"].strip()

    return company, salary

def main() -> int:
    listing_html = fetch(WATCH_URL)
    jobs = extract_jobs_from_listing(listing_html, WATCH_URL)

    conn = connect(DB_PATH)
    init_db(conn)

    new_items: list[tuple[str, str, str | None, str | None]] = []

    for title, url in jobs:
        if is_seen(conn, url):
            continue

        # Only enrich new jobs (keeps traffic low)
        company, salary = (None, None)
        try:
            company, salary = enrich_from_job_page(url)
        except Exception:
            pass

        upsert_job(conn, url, title, company, salary)
        new_items.append((title, url, company, salary))

    if not new_items:
        print("No new front-end jobs.")
        return 0

    lines = [f"🆕 {len(new_items)} new front-end job(s):"]
    for title, url, company, salary in new_items[:8]:
        extras = []
        if company: extras.append(company)
        if salary: extras.append(salary)
        extra_txt = f" ({' • '.join(extras)})" if extras else ""
        lines.append(f"- {title}{extra_txt}\n  {url}")
    if len(new_items) > 8:
        lines.append(f"...and {len(new_items)-8} more.")

    send_message(TOKEN, CHAT_ID, "\n".join(lines))
    print(f"Sent {len(new_items)} new jobs.")
    return len(new_items)

if __name__ == "__main__":
    raise SystemExit(main())
