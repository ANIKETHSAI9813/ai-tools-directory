#!/usr/bin/env python3
"""
updater.py
==========
Fetches the latest posts from tech/AI RSS feeds and merges them into the
directory's data.json file, skipping anything already present.

Standard library only -- no `pip install` required.

Usage:
    python3 updater.py
    python3 updater.py --limit 15 --data ./data.json
    python3 updater.py --feed "https://news.ycombinator.com/rss"
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
    "https://news.ycombinator.com/rss",
    # Product Hunt's public RSS endpoint (may require auth / can go offline;
    # failures here are handled gracefully and simply skipped).
    "https://www.producthunt.com/feed",
]

DEFAULT_CATEGORY = "AI & Tech"  # fallback when no keyword rule matches
DEFAULT_LIMIT = 15
REQUEST_TIMEOUT = 10  # seconds
USER_AGENT = "Mozilla/5.0 (compatible; ToolsDirectoryUpdater/1.0)"
DESCRIPTION_MAX_LEN = 200

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

# Ordered keyword -> category rules. First match wins, so put more specific
# categories before broad ones. Keep this in sync with the categories already
# used in data.json so new pills don't fragment your existing filters.
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
# Parsing
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


def parse_feed(xml_bytes: bytes, source_label: str) -> list[dict]:
    """
    Parse an RSS 2.0 document into a list of raw {title, link, description}
    dicts. Any single malformed <item> is skipped rather than aborting the
    whole feed.
    """
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        print(f"  ! could not parse feed from {source_label}: {exc}", file=sys.stderr)
        return items

    # Standard RSS 2.0 structure: <rss><channel><item>...</item></channel></rss>
    for item in root.findall(".//item"):
        title = item.findtext("title")
        link = item.findtext("link")
        description = item.findtext("description")

        if not title or not link:
            continue  # not enough data to build a usable entry

        items.append(
            {
                "title": clean_text(title),
                "link": link.strip(),
                "description": clean_text(description) or "No description available.",
            }
        )

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
    """
    Append new_candidates to existing, skipping duplicates by id, by
    affiliate_link, and by exact name match. Returns (merged_list, added_count).
    """
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
# Main
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
        print(f"    parsed {len(parsed)} item(s)")
        raw_items.extend(parsed)

    if not raw_items:
        print("No items were fetched from any feed. data.json left unchanged.")
        return

    # Respect the 10-15 (default 15) item cap on freshly parsed candidates
    # before dedup, so we don't do unnecessary work on huge feeds.
    raw_items = raw_items[: max(limit * 2, limit)]
    candidates = [to_directory_entry(item, category) for item in raw_items]

    existing = load_existing(data_path)
    merged, added = merge_entries(existing, candidates, limit=limit)

    save_data(data_path, merged)

    print(f"Added {added} new tool(s). Total entries in {data_path.name}: {len(merged)}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch tech/AI RSS feeds into data.json")
    parser.add_argument(
        "--feed",
        action="append",
        dest="feeds",
        help="Feed URL to fetch (can be passed multiple times). Defaults to built-in list.",
    )
    parser.add_argument(
        "--data",
        default="data.json",
        help="Path to the directory's data.json file (default: ./data.json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max number of new entries to add per run (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--category",
        default=None,
        help=(
            "Force this category on every new entry instead of auto-guessing "
            f'from keywords (auto-guess falls back to "{DEFAULT_CATEGORY}" if nothing matches)'
        ),
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    feeds = args.feeds if args.feeds else DEFAULT_FEEDS
    run(feeds=feeds, data_path=Path(args.data), limit=args.limit, category=args.category)


if __name__ == "__main__":
    main()
