# AI Tools Directory

[![Auto-update](https://github.com/anikethsai9813/ai-tools-directory/actions/workflows/daily_update.yml/badge.svg)](https://github.com/anikethsai9813/ai-tools-directory/actions/workflows/daily_update.yml)

A searchable list of AI and developer tools that maintains itself. A daily GitHub Action collects new launches, adds the ones that look like real tools, and removes entries whose links have died.

**Live site:** https://anikethsai9813.github.io/ai-tools-directory/

## How it updates

`updater.py` runs every day at 08:00 UTC (`.github/workflows/daily_update.yml`) and commits any change to `data.json`.

**1. Discover** — candidates come from four sources and are interleaved so no single source dominates (default cap: 60 new tools per run):

| Source | What it pulls | Quality filter |
|---|---|---|
| Hacker News | Show HN posts from the last 4 days (Algolia API) | ≥ 5 points, not an essay/game/port, has a product link |
| Product Hunt | Today's launches (Atom feed) | Uses the launch tagline as the description |
| GitHub | Repos created in the last 30 days on AI, agent, MCP, RAG, automation and dev-tool topics | ≥ 150 stars, not an "awesome list"/tutorial/paper |
| Hugging Face | Trending Spaces | ≥ 20 likes, Space is running |

Every candidate is cleaned (titles like `Name – what it does` are split into a name and description; emoji and repeated names are stripped), categorized by keyword scoring, checked against an NSFW blocklist, and de-duplicated by link and by name.

**2. Maintain** — each run re-checks 300 existing links (oldest-checked first). An entry is removed after **two consecutive** dead results (HTTP 404/410/451 or the domain no longer resolves); timeouts and bot-blocking responses don't count. Entries with a weak description get the page's meta description instead, and vote counts are refreshed from the source.

Run it locally (Python 3.10+, standard library only):

```bash
python3 updater.py                      # discover + maintain
python3 updater.py --limit 100          # more new tools per run
python3 updater.py --check 0            # skip link checks
python3 updater.py --no-discover        # maintenance only
python3 updater.py --sources hn,github  # pick sources
```

Set `GITHUB_TOKEN` to raise GitHub's search rate limit (Actions does this automatically).

## Frontend

Static HTML/CSS/JS, no framework or build step: `index.html`, `style.css`, `app.js`.

- Search matches every word in any order across name, description, category and source; name matches rank first. Press `/` to focus it.
- Three views: **Most popular** (default), **Recently added**, and **A–Z**. Popularity uses each source's own count (HN points, GitHub stars, Hugging Face likes), ranked as a percentile within that source so the sources mix fairly. Product Hunt's feed has no vote counts, so those tools sort last in that view.
- Filter by category and save tools (stored in `localStorage`).
- The search and filters are kept in the URL, so a filtered view can be shared.
- Renders 50 results at a time; follows the system light/dark setting.

Run it locally: `python3 -m http.server 8000`, then open http://localhost:8000.

## Data format

`data.json` is an array of:

```json
{
  "id": "4f1c2a9e0b7d",
  "name": "Rustable",
  "description": "Open source database client built in Rust.",
  "category": "Coding & Dev",
  "url": "https://github.com/example/rustable",
  "source": "Hacker News",
  "added": "2026-11-06",
  "votes": 104,
  "checked": "2026-11-06"
}
```

`fails` appears on an entry after a failed link check and is cleared when the link works again.

## Contributing

Suggest a tool with the [submission form](https://docs.google.com/forms/d/e/1FAIpQLSfrPhHJ8zSm2bU8mAwu8BIL1_KILEQBU2WywI3sP7SemrOt1A/viewform), or open a PR that adds an entry to `data.json`.
