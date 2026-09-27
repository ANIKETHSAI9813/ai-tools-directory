[README.md](https://github.com/user-attachments/files/32695225/README.md)
# AI Tools & Automation Directory

[![Live Demo](https://img.shields.io/badge/demo-live-6366f1?style=flat-square)](https://anikethsai9813.github.io/ai-tools-directory/)
[![Auto-update](https://github.com/anikethsai9813/ai-tools-directory/actions/workflows/daily_update.yml/badge.svg)](https://github.com/anikethsai9813/ai-tools-directory/actions/workflows/daily_update.yml)
[![No Build Step](https://img.shields.io/badge/build_step-none-8b5cf6?style=flat-square)](#tech-stack)

A curated, searchable directory of AI software and automation tools — a dependency-free static site that finds and adds new tools on its own, every day.

**🔗 Live site: [anikethsai9813.github.io/ai-tools-directory](https://anikethsai9813.github.io/ai-tools-directory/)**

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Getting Started](#getting-started)
- [Keeping the Directory Updated](#keeping-the-directory-updated)
- [Tool Data Format](#tool-data-format)
- [Customization](#customization)
- [Contributing](#contributing)
- [Affiliate Links](#affiliate-links)
- [Credits](#credits)
- [License](#license)

## Overview

AI Tools & Automation Directory is a single-page directory for discovering AI and automation software. It ships as a handful of static files — no framework, no bundler, no backend — and stays current by itself: a scheduled GitHub Action scans Hacker News' Show&nbsp;HN and Product Hunt feeds every day, auto-categorizes new launches, and commits them straight into the site's data file. As of this writing it lists **909 tools across 7 categories**, with instant client-side search, category filtering, and a login-free bookmarking system.

## Features

- 🔍 **Instant search** — filters by name, description, and category as you type (debounced, fully client-side).
- 🏷️ **Dynamic category pills** — built directly from `data.json`, so new categories show up automatically as they appear.
- ⭐ **Bookmarks** — save tools to a personal "Saved" view, persisted in `localStorage`; no account required.
- 📌 **Featured tools** — entries flagged `featured: true` are sorted to the top and get a "★ Featured" ribbon.
- 💀 **Loading, empty, and error states** — skeleton cards while data loads, a friendly empty state for no matches, and a fallback if `data.json` fails to fetch.
- 📱 **Responsive grid** — 1 / 2 / 3 columns depending on viewport, plus `focus-visible` and `prefers-reduced-motion` support.
- 🌓 **Dark, glowy UI** — dot-grid hero and gradient accents styled entirely with Tailwind's CDN build.
- 🤖 **Self-updating** — a daily GitHub Actions job pulls fresh launches from Show HN and Product Hunt, auto-categorizes them, de-dupes against existing entries, and commits the result.
- 📮 **"Submit a tool"** — a public Google Form linked from the header and footer for community submissions.
- 🔗 **Per-tool affiliate links**, with a ready-made hook for adding tracking parameters (see [Affiliate Links](#affiliate-links)).

## Tech Stack

**Frontend**
- HTML5 + vanilla JavaScript (ES6+, single IIFE module, zero dependencies)
- [Tailwind CSS](https://tailwindcss.com/) via the CDN build — theme config lives inline in `index.html`
- Google Fonts — Inter (UI) and JetBrains Mono (accents)

**Data & automation**
- `data.json` — a flat JSON array that acts as the entire database
- `updater.py` — Python 3, standard library only, zero `pip install`s
- GitHub Actions — daily cron job that runs the updater and commits changes

**Hosting**
- GitHub Pages, served directly from the repository

## Project Structure

```
ai-tools-directory/
├── index.html                   # Markup, Tailwind theme config, card/skeleton templates
├── app.js                       # All client-side logic: fetch, search, filter, bookmarks, render
├── data.json                    # The directory's data — one JSON object per tool
├── updater.py                   # Finds new tool launches and appends them to data.json
└── .github/
    └── workflows/
        └── daily_update.yml     # Scheduled job that runs updater.py and commits the result
```

## How It Works

**Frontend — `index.html` + `app.js`**
1. On load, six skeleton cards render immediately while `data.json` is fetched (`cache: 'no-store'`, so visitors always see the latest data).
2. Tools are sorted featured-first, category pills are rebuilt from whatever categories exist in the data, and the grid renders.
3. Typing in the search box filters in-browser (debounced ~120ms) against name, description, and category. Category pills and the "Saved" toggle filter further — everything happens client-side, with no server round trip.
4. Bookmarking a tool stores its id in `localStorage` (key `aiToolsDirectory.bookmarks`) and exposes it under a virtual **Saved** category.

**Automation — `updater.py` + GitHub Actions**
1. Daily at 08:00 UTC (or on demand via *Actions → Run workflow*), the workflow checks out the repo and runs `updater.py`.
2. The script downloads the Show HN and Product Hunt feeds, strips HTML from titles/descriptions, and discards anything matching a junk-title keyword list (news posts, "Ask/Tell HN" threads, benchmarks, and similar non-tool content).
3. Each remaining item gets a category from an ordered keyword rule list (falling back to `AI & Tech`) and a stable id (a short SHA-1 hash of its link).
4. New items are merged into `data.json`, skipping anything whose id, link, or name already exists, up to `--limit` (default 15) additions per run.
5. If `data.json` changed, the workflow commits and pushes it back to `main` as `tools-directory-bot`, and GitHub Pages redeploys automatically.

## Getting Started

Nothing needs installing to view the site — a modern browser is enough. Python 3 is only needed if you want to run the updater locally.

```bash
git clone https://github.com/anikethsai9813/ai-tools-directory.git
cd ai-tools-directory

# Serve it locally — opening index.html directly (file://) will fail to
# fetch data.json in most browsers, so use a tiny static server instead:
python3 -m http.server 8000
```

Then open **http://localhost:8000**. Any static file server works just as well — `npx serve`, VS Code's Live Server extension, etc.

## Keeping the Directory Updated

**Automatically (already set up)** — `.github/workflows/daily_update.yml` runs `updater.py` once a day and pushes any new tools it finds. Trigger it on demand from the repo's **Actions** tab (*Auto-update tools directory → Run workflow*), or change the schedule by editing the cron expression:

```yaml
schedule:
  - cron: "0 8 * * *"   # UTC
```

**Manually / locally**

```bash
python3 updater.py                          # pull from the default feeds, add up to 15 tools
python3 updater.py --limit 30                # raise the per-run cap
python3 updater.py --data ./data.json        # point at a specific data file
python3 updater.py --feed "<rss-or-atom-url>" # add/override a feed (repeatable)
python3 updater.py --category "Automation"   # force a category instead of auto-guessing
```

No packages to install — `updater.py` only touches the Python standard library.

## Tool Data Format

Every entry in `data.json` is a flat object:

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable unique key, used for de-duplication and as the bookmark identifier |
| `name` | string | Shown as the card title |
| `description` | string | Card body copy; auto-generated entries are truncated to ~200 characters |
| `category` | string | Any value works — the filter pills are generated from whatever's present |
| `affiliate_link` | string (URL) | Destination of the **Try Tool** button |
| `featured` | boolean | Sorts the card to the top and adds a **★ Featured** ribbon |

Example:

```json
{
  "id": "taskmagic-ai",
  "name": "TaskMagic",
  "description": "AI-powered browser automation that captures your manual web tasks once and turns them into no-code workflows you can run again and again.",
  "category": "Automation",
  "affiliate_link": "https://appsumo.8odi.net/oNbv9m",
  "featured": true
}
```

## Customization

- **Colors / theme** — edit the `tailwind.config` block at the top of `index.html` (`canvas`, `surface`, `border`, `accent.indigo`, `accent.violet`).
- **Fonts** — swap the Google Fonts `<link>` tag and the matching `fontFamily` entries next to it.
- **Feeds & categorization rules** — edit `DEFAULT_FEEDS`, `CATEGORY_RULES`, and `IGNORE_KEYWORDS` at the top of `updater.py`.
- **Update schedule** — edit the `cron` expression in `.github/workflows/daily_update.yml`.
- **Submission form** — swap the Google Form URL (it appears in both the header and footer of `index.html`).

## Contributing

- **Suggest a tool** — use the [Submit a tool](https://docs.google.com/forms/d/e/1FAIpQLSfrPhHJ8zSm2bU8mAwu8BIL1_KILEQBU2WywI3sP7SemrOt1A/viewform) form linked in the site's header and footer.
- **Add or edit an entry directly** — open a pull request adding an object to `data.json` in the [format above](#tool-data-format).
- **Code changes** — this project is dependency-free on purpose; PRs that keep it framework- and build-step-free are the easiest to merge.

## Affiliate Links

Some entries' `affiliate_link` values (for example, AppSumo deals) are affiliate URLs — noted here for transparency. `buildAffiliateUrl()` in `app.js` is also a ready-made hook for appending tracking parameters to outgoing links if needed.

## Credits

- [Tailwind CSS](https://tailwindcss.com/) (CDN build)
- [Google Fonts](https://fonts.google.com/) — Inter & JetBrains Mono
- [Hacker News (Show HN)](https://news.ycombinator.com/show) and [Product Hunt](https://www.producthunt.com/) as launch-discovery feeds

Maintained by [@anikethsai9813](https://github.com/anikethsai9813).

## License

No license file is currently included, which by default means all rights are reserved and others can't legally reuse the code. If you'd like this project to be open source, add a `LICENSE` file — [MIT](https://choosealicense.com/licenses/mit/) is a common, permissive choice for small static-site projects like this one.
