#!/usr/bin/env python3
"""
updater.py
==========
Fetches the latest software/AI product launches from tech feeds and merges
them into the directory's data.json file, skipping duplicates and news articles.

Standard library only -- no `pip install` required.

Usage:
    python3 updater.py
    python3 updater.py --limit 15 --data ./data.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_FEEDS = [
    # Show HN feed specifically targets creator product launches rather than general news
    "https://news.ycombinator.com/showrss",
    # Product Hunt public RSS/Atom feed
    "https://www.producthunt.com/feed",
]

DEFAULT_CATEGORY = "AI & Tech"  # fallback when no keyword rule matches
DEFAULT_LIMIT = 15
REQUEST_TIMEOUT = 10  # seconds
USER_AGENT = "Mozilla/5.0 (compatible; ToolsDirectoryUpdater/1.0)"
DESCRIPTION_MAX_LEN = 200

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

# Keywords in titles that indicate non-tool entries (news, blog posts, essays)
IGNORE_KEYWORDS = [
    "earthquake", "ask hn", "tell hn", "why i", "my thoughts",
    "position on", "security content", "boiling water", "translation wins",
    "benchmarking", "gpu", "macos", "golang", "study finds", "report:"
]

# Ordered keyword -> category rules. First match wins.
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Automation", ["automat", "workflow", "agent", "scrape", "rpa", "zapier", "no-code", "no code"]),
    ("Marketing & Social", ["marketing", "social media", "seo", "influencer", "ugc", "webinar", "summit", "email campaign"]),
    ("Video & Audio", ["video", "audio", "podcast", "voice", "avatar", "transcri"]),
    ("Image & Design", ["image", "design", "photo", "graphic", "illustration", "logo"]),
    ("Text & Writing", ["writ", "content", "blog", "copy", "ebook", "book", "script"]),
    ("Productivity", ["productiv", "task", "notion", "workspace", "invoice", "receipt", "parser", "document", "notebook"]),
    ("Coding & Dev", ["code", "developer", "api", "github", "programming", "ide"]),
]


def guess_category(title: str, description: str) -> str:
    """Best-effort category guess from keywords in the title/description."""
    haystack = f"{title} {description}".lower()
    for category, keywords in CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category
    return DEFAULT_CATEGORY


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_feed(url: str) -> bytes | None:
    """Download raw RSS/XML bytes from a feed URL. Returns None on failure."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"  ! could not fetch {url}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Parsing & Filtering
# ---------------------------------------------------------------------------

def clean_text(raw: str | None) -> str:
    """Strip HTML tags/entities and collapse whitespace from feed text."""
    if not raw:
        return ""
    text = unescape(raw)
    text = TAG_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def truncate(text: str, max_len: int = DESCRIPTION_MAX_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def is_junk_title(title: str) -> bool:
    """Returns True if the title matches known non-tool news/article patterns."""
    t_lower = title.lower()
    return any(keyword in t_lower for keyword in IGNORE_KEYWORDS)


def parse_feed(xml_bytes: bytes, source_label: str) -> list[dict]:
    """Parse RSS 2.0 or Atom feeds into clean tool entries."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        print(f"  ! could not parse feed from {source_label}: {exc}", file=sys.stderr)
        return items

    # 1. Standard RSS 2.0 (<item> elements)
    for item in root.findall(".//item"):
        title = item.findtext("title")
        link = item.findtext("link")
        description = item.findtext("description")

        if not title or not link:
            continue

        cleaned_title = clean_text(title)
        # Strip "Show HN: " prefix if present
        cleaned_title = re.sub(r"^Show HN:\s*", "", cleaned_title, flags=re.IGNORECASE)

        if is_junk_title(cleaned_title):
            continue

        cleaned_desc = clean_text(description)
        if not cleaned_desc or cleaned_desc.lower() in ["comments", "no description available."]:
            cleaned_desc = f"{cleaned_title} - AI software and productivity tool."

        items.append({
            "title": cleaned_title,
            "link": link.strip(),
            "description": cleaned_desc,
        })

    # 2. Atom Feed (<entry> elements, used by Product Hunt)
    atom_entries = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//entry")
    for entry in atom_entries:
        title_elem = entry.find("{http://www.w3.org/2005/Atom}title") if entry.find("{http://www.w3.org/2005/Atom}title") is not None else entry.find("title")
        title = title_elem.text if title_elem is not None else None

        link = None
        for l_elem in entry.findall("{http://www.w3.org/2005/Atom}link"):
            if l_elem.get("rel") in (None, "alternate"):
                link = l_elem.get("href")
                break

        if not title or not link:
            continue

        cleaned_title = clean_text(title)
        if is_junk_title(cleaned_title):
            continue

        summary_elem = entry.find("{http://www.w3.org/2005/Atom}summary") or entry.find("summary")
        cleaned_desc = clean_text(summary_elem.text) if summary_elem is not None else f"{cleaned_title} - AI tool launch."

        items.append({
            "title": cleaned_title,
            "link": link.strip(),
            "description": cleaned_desc,
        })

    return items


# ---------------------------------------------------------------------------
# Transformation
# ---------------------------------------------------------------------------

def make_id(link: str) -> str:
    """Deterministic short unique id derived from the item's link."""
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:12]


def to_directory_entry(raw_item: dict, category: str | None = None) -> dict:
    resolved_category = category or guess_category(raw_item["title"], raw_item["description"])
    return {
        "id": make_id(raw_item["link"]),
        "name": raw_item["title"],
        "description": truncate(raw_item["description"]),
        "category": resolved_category,
        "affiliate_link": raw_item["link"],
        "featured": False,
    }


# ---------------------------------------------------------------------------
# data.json I/O
# ---------------------------------------------------------------------------

def load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            print(f"  ! {path} does not contain a JSON list; starting fresh.", file=sys.stderr)
            return []
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  ! could not read {path}: {exc}", file=sys.stderr)
        return []


def save_data(path: Path, data: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def merge_entries(existing: list[dict], new_candidates: list[dict], limit: int) -> tuple[list[dict], int]:
    existing_ids = {e.get("id") for e in existing if e.get("id")}
    existing_links = {e.get("affiliate_link") for e in existing if e.get("affiliate_link")}
    existing_names = {e.get("name", "").strip().lower() for e in existing}

    merged = list(existing)
    added = 0

    for candidate in new_candidates:
        if added >= limit:
            break
        if candidate["id"] in existing_ids:
            continue
        if candidate["affiliate_link"] in existing_links:
            continue
        if candidate["name"].strip().lower() in existing_names:
            continue

        merged.append(candidate)
        existing_ids.add(candidate["id"])
        existing_links.add(candidate["affiliate_link"])
        existing_names.add(candidate["name"].strip().lower())
        added += 1

    return merged, added


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------

def run(feeds: list[str], data_path: Path, limit: int, category: str) -> None:
    print(f"Fetching up to {limit} new tools from {len(feeds)} feed(s)...")

    raw_items: list[dict] = []
    for feed_url in feeds:
        print(f"- {feed_url}")
        xml_bytes = fetch_feed(feed_url)
        if xml_bytes is None:
            continue
        parsed = parse_feed(xml_bytes, source_label=feed_url)
        print(f"    parsed {len(parsed)} valid product item(s)")
        raw_items.extend(parsed)

    if not raw_items:
        print("No tool items were fetched. data.json left unchanged.")
        return

    candidates = [to_directory_entry(item, category) for item in raw_items]
    existing = load_existing(data_path)
    merged, added = merge_entries(existing, candidates, limit=limit)

    save_data(data_path, merged)
    print(f"Added {added} new tool(s). Total entries in {data_path.name}: {len(merged)}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch software launches into data.json")
    parser.add_argument("--feed", action="append", dest="feeds", help="Feed URL to fetch.")
    parser.add_argument("--data", default="data.json", help="Path to data.json")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max items to add")
    parser.add_argument("--category", default=None, help="Force category")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    feeds = args.feeds if args.feeds else DEFAULT_FEEDS
    run(feeds=feeds, data_path=Path(args.data), limit=args.limit, category=args.category)


if __name__ == "__main__":
    main()
