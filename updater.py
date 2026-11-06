#!/usr/bin/env python3
"""
updater.py — keeps data.json fresh. Standard library only.

Each run does two things:

1. Discover: pull new launches from several sources, keep the ones that look
   like real tools, categorize them, de-duplicate, and append them.
     - Hacker News "Show HN" (Algolia API, only posts with some upvotes)
     - Product Hunt (Atom feed, uses the tagline as the description)
     - GitHub (new repos on AI/automation/dev-tool topics with real traction)
     - Hugging Face Spaces (trending AI apps)

2. Maintain: re-check a batch of existing links. Entries whose link is dead
   (404/410, domain gone) on two consecutive checks are removed. Entries with
   a weak description get the page's meta description instead.

Usage:
    python3 updater.py                  # discover + maintain
    python3 updater.py --limit 60       # cap on new tools per run
    python3 updater.py --check 300      # how many links to re-check per run
    python3 updater.py --no-discover    # maintenance only
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

USER_AGENT = "Mozilla/5.0 (compatible; AIToolsDirectoryBot/2.0; +https://github.com/anikethsai9813/ai-tools-directory)"
TIMEOUT = 12
DESC_MAX = 180
TODAY = dt.date.today().isoformat()

# ---------------------------------------------------------------------------
# Categories — every category scores keyword hits in the name/description and
# the highest score wins (ties go to the earlier category). "Chat & LLMs" is a
# catch-all for generic AI wording, so it only wins when nothing else matches.
# Word-boundary regexes so "ide" doesn't match "side" and "api" not "rapid".
# ---------------------------------------------------------------------------

CATEGORIES: list[tuple[str, str]] = [
    ("Agents & Automation", r"agents?|agentic|automat\w*|workflows?|mcp|rpa|zapier|n8n|make\.com|scrap(?:e|er|ers|ing)|crawl\w*|browser use|computer use|orchestrat\w*|bots?|no.code|low.code|autonomous|headless browser"),
    ("Coding & Dev", r"code|coding|coder|codebase|developers?|devtools?|api|apis|sdk|cli|ide|github|git|compiler|debug\w*|framework|database|sql|postgres|sqlite|terminal|deploy\w*|docker|kubernetes|k8s|rust|python|typescript|javascript|golang|llvm|runtime|backend|frontend|devops|ci/cd|regex|json|wasm|vs ?code|cursor|repos?|pull requests?|prs|tui|linux|macos|windows|shell|bash|zsh|proxy|monitor\w*|react|dom|css|html|plugins?|extensions?|self.hosted|open.source|servers?|converter|parser|editor|neovim|vim|emacs|kernel|firmware|pcb|embedded|plc|benchmark\w*|observability|logs?|tracing|status line|dotfiles|package manager|build"),
    ("Video & Audio", r"video|videos|audio|podcasts?|voice|speech|music|songs?|sound|transcri\w*|dubbing|text.to.speech|tts|avatars?|youtube|subtitles?|phone calls?|lip.?sync"),
    ("Image & Design", r"images?|photos?|photograph\w*|design|designs|designer\w*|graphic design|illustrat\w*|logos?|figma|ui kit|icons|diffusion|3d|svg|fonts?|drawings?|sketch\w*|t2i|text.to.image|image editing|wallpapers?|cad|mockups?"),
    ("Writing", r"writ(?:e|er|ers|ing)|copywrit\w*|blogs?|grammar|paraphras\w*|translat\w*|ebooks?|novels?|newsletters?|humaniz\w*|proofread\w*|essays?"),
    ("Marketing & Sales", r"marketing|seo|geo|social media|ads|advertis\w*|sales|crm|leads?|outreach|cold email|influencers?|ugc|landing pages?|ecommerce|e.commerce|shopify|linkedin|tiktok|instagram|brand\w*"),
    ("Data & Research", r"data|datasets?|analytics|research\w*|rag|embeddings?|vector|knowledge base|pdfs?|papers?|arxiv|spreadsheets?|excel|csv|charts?|dashboards?|finance|financial|stocks?|trading|semantic search|sql"),
    ("Productivity", r"productiv\w*|tasks?|todos?|notes|note.taking|calendar|meetings?|email|inbox|workspace|notion|documents?|invoices?|resumes?|schedul\w*|focus|habits?|bookmarks?|clipboard|launcher|journal\w*|memory|personal assistant|erp|messaging|team chat|crm|password\w*|privacy|backup\w*"),
    ("Chat & LLMs", r"llms?|gpt\w*|chatgpt|claude|gemini|llama|mistral|deepseek|qwen|chat\w*|assistants?|copilot|prompts?|models?|inference|fine.tun\w*|ai|ml|neural|transformers?|webgpu|on.device|local(?:ly)?"),
]
CATEGORY_RES = [(name, re.compile(rf"\b(?:{pat})\b", re.I)) for name, pat in CATEGORIES]
CATCH_ALL = "Chat & LLMs"
OTHER = "Other"

# Signals that the item is AI/automation related (used to gate the noisier sources).
AI_RE = re.compile(
    r"\b(ai|a\.i\.|llms?|gpt\w*|chatgpt|claude|gemini|llama|mistral|deepseek|qwen|openai|anthropic|"
    r"agents?|agentic|mcp|rag|embeddings?|inference|fine.tun\w*|neural|diffusion|machine learning|ml|"
    r"copilot|prompts?|automat\w*|workflows?|transcri\w*|text.to.\w+|speech.to.text|vision|ocr|"
    r"generative|genai|models?|chatbots?|assistants?|semantic|vector)\b", re.I)

# Never list these, from any source.
NSFW_RE = re.compile(r"\b(nsfw|uncensored|nude\w*|nudify|undress\w*|porn\w*|hentai|explicit|erotic\w*|sexy|onlyfans|cum|"
                     r"face.?swap|head.?swap|deepfake\w*|jailbreak\w*|casino|betting|crypto.?pump)\b", re.I)

# Titles that are almost never tools.
JUNK_RE = re.compile(
    r"^(ask|tell|launch) hn\b|^(i|we) (spent|tried|got|reverse\w*|turned|ported|wanted|hacked|tracked|put|analy[sz]ed|scraped|asked|benchmarked|measured|found|read|ran|taught|trained)\b"
    r"|^(my|how|why|what|when|this|after|from|on|in|learning|hacking|measuring|collected)\b"
    r"|\b(games?|puzzles?|chess|sudoku|crossword|wordle|doom|tetris|emulator|snes|nes|retro|demoscene|essay|blog post|"
    r"thoughts on|lessons from|post.mortem|interview|podcast episode|newsletter issue|course|tutorial|books?|"
    r"jobs? board|hiring|portfolio|wallpapers?|recipes?|simulator|minecraft|running on|running as|ported)\b", re.I)

# "Name – tagline". U+FFFD covers en-dashes that were mangled in older data.
SEP_RE = re.compile(r"\s+[–—\-\ufffd]\s+|:\s+|,\s+|\s*\|\s*")
BRAG_RE = re.compile(r"^(i|we)\s+(built|made|wrote|created|launched|open.sourced)\s+(an?\s+|the\s+|my\s+)?", re.I)
GENERIC_HOSTS = {"github.com", "gitlab.com", "codeberg.org", "huggingface.co", "apps.apple.com", "play.google.com",
                 "chromewebstore.google.com", "addons.mozilla.org", "youtube.com", "news.ycombinator.com",
                 "npmjs.com", "pypi.org", "crates.io", "marketplace.visualstudio.com", "sr.ht", "git.sr.ht"}
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
META_RE = re.compile(
    r"""<meta\s+[^>]*?(?:name|property)\s*=\s*["'](?:og:description|description|twitter:description)["'][^>]*?content\s*=\s*["']([^"']{20,})["']"""
    r"""|<meta\s+[^>]*?content\s*=\s*["']([^"']{20,})["'][^>]*?(?:name|property)\s*=\s*["'](?:og:description|description|twitter:description)["']""",
    re.I | re.S)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def clean(raw: str | None) -> str:
    if not raw:
        return ""
    text = TAG_RE.sub(" ", unescape(unescape(raw)))
    return WS_RE.sub(" ", text).strip()


def truncate(text: str, n: int = DESC_MAX) -> str:
    text = text.strip()
    if len(text) <= n:
        return text
    cut = text[: n - 1]
    # prefer to cut at a sentence or word boundary
    for mark in (". ", "; ", ", ", " "):
        i = cut.rfind(mark)
        if i > n * 0.6:
            cut = cut[:i]
            break
    return cut.rstrip(" .,;:") + "…"


def sentence_case(text: str) -> str:
    text = text.strip().rstrip(".")
    if not text:
        return text
    end = "" if text[-1] in "?!…" else "."
    return text[0].upper() + text[1:] + end


def http_get(url: str, accept: str = "*/*", headers: dict | None = None, limit: int | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.status, resp.read(limit) if limit else resp.read()


def get_json(url: str, headers: dict | None = None):
    try:
        return json.loads(http_get(url, "application/json", headers)[1])
    except Exception as exc:  # noqa: BLE001 — a failing source must never break the run
        log(f"  ! {url[:90]}: {exc}")
        return None


def normalize_url(url: str) -> str:
    p = urllib.parse.urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/").lower()
    return f"{host}{path}"


def norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def make_id(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()[:12]


def categorize(name: str, desc: str = "", extra: str = "") -> str:
    best, best_score = OTHER, 0.0
    for cat, rx in CATEGORY_RES:
        # name hits count double; distinct words only, so one repeated word can't dominate
        score = 2 * len(set(m.lower() for m in rx.findall(name))) + len(set(m.lower() for m in rx.findall(f"{desc} {extra}")))
        if cat == CATCH_ALL:
            score = min(score, 0.5)
        if score > best_score:
            best, best_score = cat, score
    return best


def split_title(title: str) -> tuple[str, str]:
    """'Stroq – a local audit of X' -> ('Stroq', 'A local audit of X.')"""
    title = re.sub(r"^show hn:\s*", "", clean(title), flags=re.I)
    parts = SEP_RE.split(title, maxsplit=1)
    if len(parts) == 2:
        name, tag = parts[0].strip(), parts[1].strip()
        balanced = name.count("(") == name.count(")")
        via_comma = SEP_RE.search(title).group().strip() == ","
        if via_comma and not re.match(r"(an?|the|your|my|open.source|free|self.hosted)\b", tag, re.I):
            return title, ""
        if balanced and 1 <= len(name.split()) <= 5 and len(name) <= 40 and len(tag) >= 8:
            return name, sentence_case(tag)
    return title, ""


def name_from_url(url: str) -> str:
    """Best guess at a product name from its link: repo name, or the domain's main label."""
    p = urllib.parse.urlsplit(url)
    host = p.netloc.lower().removeprefix("www.")
    segs = [x for x in p.path.split("/") if x]
    if host in GENERIC_HOSTS or host.endswith((".github.io", ".gitlab.io", ".vercel.app", ".netlify.app", ".pages.dev")):
        if host in GENERIC_HOSTS:
            return segs[-1] if len(segs) >= 2 and host != "apps.apple.com" else (segs[1] if len(segs) > 1 else "")
        sub = host.split(".")[0]
        return segs[0] if segs and host.endswith(".github.io") else sub
    labels = host.split(".")
    main = labels[-2] if len(labels) >= 2 else labels[0]
    if main in ("co", "com", "org", "net") and len(labels) >= 3:
        main = labels[-3]
    return main.capitalize() if main.islower() else main


def parse_launch(title: str, url: str) -> tuple[str, str] | None:
    """Turn a launch title into (name, description), or None if it isn't a tool."""
    title = re.sub(r"^show hn:\s*", "", clean(title), flags=re.I)
    if JUNK_RE.search(title) or NSFW_RE.search(title):
        return None
    name, tag = split_title(title)
    if tag:
        return name, tag
    # No "Name – tagline": use the link for the name and the title as the description.
    desc = BRAG_RE.sub("", title)
    name = name_from_url(url)
    if not name or len(name) < 2 or len(desc.split()) < 3:
        return None
    return name, sentence_case(desc)


EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]+")


def tidy_description(name: str, desc: str) -> str:
    desc = EMOJI_RE.sub("", clean(desc)).strip(" -–—:|")
    # drop a leading "Name:" / "Name -" / "Name is" the description often repeats
    m = re.match(rf"^\s*{re.escape(name)}\s*(?:[:\-–—|]|is an?|is the)\s+", desc, re.I)
    if m and len(desc) - m.end() > 15:
        desc = desc[m.end():]
    return truncate(sentence_case(WS_RE.sub(" ", desc))) if desc else ""


def entry(name: str, desc: str, url: str, source: str, category: str | None = None, votes: int | None = None) -> dict:
    name = EMOJI_RE.sub("", clean(name)).strip()
    desc = tidy_description(name, desc)
    e = {
        "id": make_id(url),
        "name": name.strip()[:60],
        "description": desc,
        "category": category or categorize(name, desc),
        "url": url.strip(),
        "source": source,
        "added": TODAY,
    }
    if votes is not None:
        e["votes"] = int(votes)  # HN points / GitHub stars / HF likes — powers "Most popular"
    return e


# ---------------------------------------------------------------------------
# Sources — each returns a list of candidate entries, best first.
# ---------------------------------------------------------------------------

def src_hacker_news(days: int = 4, min_points: int = 5) -> list[dict]:
    since = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).timestamp())
    url = ("https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&hitsPerPage=500"
           f"&numericFilters=points>={min_points},created_at_i>{since}")
    data = get_json(url) or {}
    out = []
    for hit in sorted(data.get("hits", []), key=lambda h: -(h.get("points") or 0)):
        link = hit.get("url")
        if not link or "news.ycombinator.com" in link:
            continue
        parsed = parse_launch(hit.get("title") or "", link)
        if not parsed:
            continue
        name, tagline = parsed
        e = entry(name, tagline, link, "Hacker News", votes=hit.get("points") or 0)
        if e["category"] == OTHER:  # use the post body for a better guess
            e["category"] = categorize(name, f"{tagline} {clean(hit.get('story_text'))[:400]}")
        out.append(e)
    return out


def src_product_hunt() -> list[dict]:
    ns = {"a": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(http_get("https://www.producthunt.com/feed", "application/atom+xml")[1])
    except Exception as exc:  # noqa: BLE001
        log(f"  ! product hunt: {exc}")
        return []
    out = []
    for e in root.findall("a:entry", ns):
        title = clean(e.findtext("a:title", "", ns))
        link_el = e.find("a:link[@rel='alternate']", ns)
        content = e.findtext("a:content", "", ns)
        m = re.search(r"<p>\s*(.*?)\s*</p>", unescape(content), re.S)
        tagline = clean(m.group(1)) if m else ""
        if not title or link_el is None or not tagline:
            continue
        out.append(entry(title, tagline, link_el.get("href"), "Product Hunt"))
    return out


# Unauthenticated search allows 10 requests/minute; GITHUB_TOKEN (set in Actions) allows 30.
GITHUB_TOPICS = ["llm", "ai-agents", "generative-ai", "mcp", "rag", "automation",
                 "ai-tools", "local-llm", "text-to-speech", "developer-tools"]


def src_github(days: int = 30, min_stars: int = 150) -> list[dict]:
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    pause = 0.5 if "Authorization" in headers else 6.5
    seen, repos = set(), []
    for i, topic in enumerate(GITHUB_TOPICS):
        if i:
            time.sleep(pause)
        q = urllib.parse.quote(f"topic:{topic} created:>={since} stars:>={min_stars} archived:false")
        data = get_json(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=30", headers)
        for r in (data or {}).get("items", []):
            if r["id"] not in seen:
                seen.add(r["id"])
                repos.append(r)
    out = []
    for r in sorted(repos, key=lambda r: -r["stargazers_count"]):
        desc = clean(r.get("description"))
        if not desc or len(desc) < 15 or r.get("fork"):
            continue
        # "awesome lists", tutorials and paper code aren't tools
        if re.search(r"\b(awesome|list of|curated|tutorial|course|roadmap|interview|paper|survey|homework|learning notes)\b",
                     f"{r['name']} {desc}", re.I):
            continue
        if re.search(r"[぀-ヿ一-鿿가-힯]", desc):  # non-English description
            continue
        name = r["name"]
        topics = " ".join(r.get("topics") or [])
        out.append(entry(name, desc, r["html_url"], "GitHub", categorize(r["name"], desc, topics),
                         votes=r["stargazers_count"]))
    return out


def src_huggingface(limit: int = 80) -> list[dict]:
    data = get_json(f"https://huggingface.co/api/spaces?sort=trendingScore&direction=-1&limit={limit}&full=true") or []
    out = []
    for s in data:
        card = s.get("cardData") or {}
        desc = clean(card.get("short_description"))
        if not desc or (s.get("likes") or 0) < 20:
            continue
        if s.get("runtime", {}).get("stage") in ("PAUSED", "SLEEPING_ERROR", "RUNTIME_ERROR", "BUILD_ERROR"):
            continue
        name = clean(card.get("title")) or s["id"].split("/")[-1]
        if re.search(r"\b(leaderboard|arena|blog|handbook|guide|paper|course)\b", f"{name} {desc}", re.I):
            continue
        out.append(entry(name, desc, f"https://huggingface.co/spaces/{s['id']}", "Hugging Face",
                         votes=s.get("likes") or 0))
    return out


SOURCES = {
    "hn": src_hacker_news,
    "producthunt": src_product_hunt,
    "github": src_github,
    "huggingface": src_huggingface,
}


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------

def interleave(lists: list[list[dict]]) -> list[dict]:
    """Round-robin across sources so one noisy source can't eat the whole quota."""
    out, i = [], 0
    while any(i < len(lst) for lst in lists):
        out.extend(lst[i] for lst in lists if i < len(lst))
        i += 1
    return out


def merge(existing: list[dict], candidates: list[dict], limit: int) -> int:
    candidates = [c for c in candidates if not NSFW_RE.search(f"{c['name']} {c['description']} {c['url']}")]
    ids = {e["id"] for e in existing}
    urls = {normalize_url(e["url"]) for e in existing}
    names = {norm_name(e["name"]) for e in existing}
    added = 0
    for c in candidates:
        if added >= limit:
            break
        key_url, key_name = normalize_url(c["url"]), norm_name(c["name"])
        if c["id"] in ids or key_url in urls or not key_name or key_name in names:
            continue
        existing.append(c)
        ids.add(c["id"]); urls.add(key_url); names.add(key_name)
        added += 1
    return added


# ---------------------------------------------------------------------------
# Maintenance — dead-link removal + description enrichment
# ---------------------------------------------------------------------------

DEAD_CODES = {404, 410, 451}
# Hosts whose pages block bots; a 403/429 there says nothing about the tool.
SKIP_META_HOSTS = ("producthunt.com",)


def probe(url: str) -> tuple[str, str]:
    """Returns (status, meta_description). status is 'ok', 'dead' or 'unknown'."""
    try:
        _, body = http_get(url, "text/html,*/*;q=0.8", limit=200_000)
    except urllib.error.HTTPError as exc:
        return ("dead" if exc.code in DEAD_CODES else "unknown"), ""
    except urllib.error.URLError as exc:
        reason = str(exc.reason).lower()
        gone = any(s in reason for s in ("name or service not known", "nodename nor servname",
                                         "getaddrinfo failed", "no address associated", "connection refused"))
        return ("dead" if gone else "unknown"), ""
    except Exception:  # noqa: BLE001 — timeouts, resets, TLS oddities
        return "unknown", ""
    m = META_RE.search(body.decode("utf-8", "ignore"))
    meta = clean((m.group(1) or m.group(2))) if m else ""
    return "ok", meta


def fetch_votes(e: dict) -> int | None:
    """Current popularity count from the entry's source, or None if unavailable."""
    url, src = e["url"], e.get("source")
    if src == "Hacker News":
        q = urllib.parse.quote(url, safe="")
        data = get_json(f"https://hn.algolia.com/api/v1/search?query={q}&restrictSearchableAttributes=url&tags=show_hn&hitsPerPage=5")
        hits = [h for h in (data or {}).get("hits", []) if normalize_url(h.get("url") or "") == normalize_url(url)]
        return max((h.get("points") or 0) for h in hits) if hits else None
    if src == "GitHub":
        m = re.match(r"https://github\.com/([^/]+/[^/#?]+)", url)
        headers = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"} if os.environ.get("GITHUB_TOKEN") else None
        data = get_json(f"https://api.github.com/repos/{m.group(1)}", headers) if m else None
        return data.get("stargazers_count") if data else None
    if src == "Hugging Face":
        sid = url.split("/spaces/", 1)[-1]
        data = get_json(f"https://huggingface.co/api/spaces/{sid}")
        return data.get("likes") if data else None
    return None


def weak_description(e: dict) -> bool:
    d = e.get("description", "")
    return len(d) < 25 or norm_name(d).startswith(norm_name(e["name"])) and len(d) < len(e["name"]) + 25


def maintain(data: list[dict], batch: int) -> tuple[int, int]:
    # Oldest-checked first; never-checked entries come first of all.
    todo = sorted(data, key=lambda e: e.get("checked", ""))[:batch]
    removed = enriched = 0
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        results = dict(zip((e["id"] for e in todo), pool.map(lambda e: probe(e["url"]), todo)))
        votes = dict(zip((e["id"] for e in todo), pool.map(fetch_votes, todo)))
    dead_ids = set()
    for e in todo:
        status, meta = results[e["id"]]
        e["checked"] = TODAY
        if votes[e["id"]] is not None:
            e["votes"] = max(votes[e["id"]], e.get("votes", 0))
        if status == "dead":
            e["fails"] = e.get("fails", 0) + 1
            if e["fails"] >= 2 and not e.get("featured"):
                dead_ids.add(e["id"])
            continue
        if status == "ok":
            e.pop("fails", None)
            host = urllib.parse.urlsplit(e["url"]).netloc
            if meta and weak_description(e) and not any(h in host for h in SKIP_META_HOSTS) \
                    and not re.search(r"contribute to .* development by creating an account", meta, re.I):
                e["description"] = tidy_description(e["name"], meta)
                enriched += 1
    if dead_ids:
        for e in [x for x in data if x["id"] in dead_ids]:
            log(f"  - removed dead link: {e['name']} ({e['url']})")
        data[:] = [x for x in data if x["id"] not in dead_ids]
        removed = len(dead_ids)
    return removed, enriched


# ---------------------------------------------------------------------------
# I/O + main
# ---------------------------------------------------------------------------

def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    for e in data:  # migrate the old schema
        if "url" not in e and "affiliate_link" in e:
            e["url"] = e.pop("affiliate_link")
        e.pop("affiliate_link", None)
    return data


def save(path: Path, data: list[dict]) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data.json")
    ap.add_argument("--limit", type=int, default=60, help="max new tools per run")
    ap.add_argument("--check", type=int, default=300, help="links to re-check per run (0 = off)")
    ap.add_argument("--sources", default=",".join(SOURCES), help="comma list: " + ",".join(SOURCES))
    ap.add_argument("--no-discover", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.data)
    data = load(path)
    start = len(data)
    log(f"Loaded {start} tools from {path}")

    if not args.no_discover:
        lists = []
        for key in args.sources.split(","):
            found = SOURCES[key.strip()]()
            log(f"- {key}: {len(found)} candidates")
            lists.append(found)
        added = merge(data, interleave(lists), args.limit)
        log(f"Added {added} new tools")

    if args.check:
        removed, enriched = maintain(data, args.check)
        log(f"Checked {min(args.check, len(data) + removed)} links: removed {removed} dead, improved {enriched} descriptions")

    save(path, data)
    log(f"Total: {len(data)} tools (was {start})")


if __name__ == "__main__":
    main(sys.argv[1:])
