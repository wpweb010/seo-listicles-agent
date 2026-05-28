# SEO Listicles Agent

A local web tool that finds **listicle pages** (Google SERP results listing companies) for any keyword, automatically detects whether **your domain** is listed on each page, and exports everything to Excel — grouped per company across multiple keyword searches.

Built for SEO outreach teams that need to track where their company is mentioned across competitor blogs, aggregators, and service pages.

**Now with a full dashboard:** sidebar navigation, per-company stats with charts, API-key management with usage tracking, bulk keyword search, and one-click view of cached search results.

---

## Why it exists

Manually checking 10+ listicles for each keyword × multiple keywords × multiple company brands = hours of tedious work. This agent does it in under a minute:

- Queries Google SERP via [Serper.dev](https://serper.dev/) (2,500 free queries/month)
- Classifies each result into **Listicle / Service Page / Aggregator / Video**
- Fetches each listicle, scans for your domain or company name (with smart variant matching)
- Reports your **position on the page** + whether it's a **Backlink** or **Mention**
- Tracks history per company, exports consolidated Excel reports

---

## Quick start

### 1. Install

```bash
git clone https://github.com/wpweb010/seo-listicles-agent.git
cd seo-listicles-agent
pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure API keys

Edit `.env` and add at minimum:

```
SERPER_API_KEY=your_serper_dev_key_here
OPENPAGERANK_KEY=your_opr_key_here   # optional, for authority scores
```

- **Serper.dev** — Sign up at https://serper.dev/, free 2,500 queries/month.
- **Open PageRank** — https://www.domcop.com/openpagerank/ (free authority proxy).

### 3. Run

```bash
python -m uvicorn api:app --port 8000
```

Open **http://localhost:8000** in your browser.

---

## How the agent works

### Flow diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  USER INPUT                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Keyword: "Top WordPress development companies India"               │ │
│  │ Company: WPWeb Infotech (auto-loads variants for detection)        │ │
│  │ Region:  India   Target: 10 listicles   Max pages: 20              │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  1. SERP FETCH  (smart pagination — stops at N listicles)               │
│     • Serper.dev → page 1, page 2, ...                                  │
│     • Each result classified:                                            │
│         - Aggregator   (Clutch, G2, GoodFirms, …)                       │
│         - Service Page (own service pages: /services/, /wp-dev/, …)     │
│         - Listicle     (blog posts / "Top N …" pages)                   │
│         - Video        (YouTube, Vimeo, …)                              │
│     • Stops when target_listicles is reached                            │
└─────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  2. DOMAIN DETECTION  (per listicle page)                               │
│     • Fetch HTML (proper User-Agent, no Brotli encoding)                │
│     • Bot-protection check (Reddit, Cloudflare) → mark "Check Manually" │
│     • Search for ALL company name variants:                              │
│         "wpwebinfotech.com" · "wpwebinfotech" · "WPWeb Infotech"        │
│         "WP Web Infotech" · "WPWEB Infotech" · custom variants          │
│     • Word-boundary + compact-text match (no false positives)            │
│     • Position detection strategies (in order):                          │
│         1. Numbered headings <h2>1. Company Name</h2>                    │
│         2. Numbered headings inside <span> wrappers (LinkedIn style)     │
│         3. Heading order on the page (skip H1 page title)                │
│         4. Numbered text patterns ("1. CompanyName")                     │
│         5. <ol> ordered list items                                       │
│         6. External company <a href> links in order                      │
│         7. Bold company names in <strong>/<b>                            │
│     • Link type: Backlink (wrapped in <a>) or Mention (text only)        │
└─────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  3. STORAGE  (SQLite — search_history.db)                               │
│     companies  — Company profiles + name variants                       │
│     keywords   — Unique keyword + region combos (with SERP hash)         │
│     searches   — Each search run, linked to company                      │
│     results    — Every URL with status, position, link type              │
└─────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  4. EXPORT  (Excel — single sheet, multi-keyword grouped)               │
│     Filename:  WPWeb_Infotech_Outreach_2026-05-27_Wednesday.xlsx        │
│     Title row: Outreach Report — WPWeb Infotech (wpwebinfotech.com)     │
│     Columns:   Keyword & Location · Domain · Pages · Page Type ·         │
│                Status · Position · Link Type · Notes                     │
│     • Keyword shown once per group (bold)                                │
│     • Empty row separator between keyword groups                         │
│     • Color-coded Page Type + Status cells                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Color legend

| Page Type | Color | Meaning |
|---|---|---|
| Aggregator | 🟠 Orange | Clutch, G2, GoodFirms — directory/marketplace |
| Service Page | 🟣 Purple | Competitor's own service page (no list) |
| Listicle (blog post / Top-Best) | 🔵 Blue | Main outreach target |
| Video | 🌸 Pink | YouTube, Vimeo — not a listicle |
| Possible listicle | 🟡 Yellow | Uncertain — verify with 🔍 button |

| Status | Color | Meaning |
|---|---|---|
| Listed | 🟢 Green | Your domain found on this page (with position) |
| _(blank)_ | ⬜ White | Domain not on this page |
| Check Manually | 🟡 Yellow | Bot-protected page (Reddit etc.) |

---

## Workflow

### 1. Add company profile (one-time)

In the **Companies** panel, click `+ Add Company`:
- **Name**: `WPWeb Infotech`
- **Domain**: `wpwebinfotech.com`
- **Custom variants** (optional): `WPWeb`, `WP Web Infotech`, etc.

The agent auto-generates variants (uppercase, lowercase, no-spaces) and adds your custom ones. These are searched on every page so non-backlinked mentions like "WPWEB Infotech" or "WP Web" are detected.

### 2. Run keyword searches

From the company card, click **`+ New Search`**. The company auto-selects in the form. Enter a keyword and submit. Repeat for as many keywords as you want — all link to the same company.

### 3. Export

Click **⬇ Export** on the company card to get one Excel file with all keyword searches grouped together. The dialog lets you:
- **Export ALL** — every search for that company
- **Export Selected** — checkbox specific keywords for a partial report

### 4. Verify any result

Click the 🔍 icon next to any row in the live results table to:
- Re-fetch the URL fresh (no cache)
- See exactly what variants were found in the HTML
- See the page's H1-H4 headings (with your domain highlighted in green)
- Get an audit trail you can trust

---

## Project structure

```
seo-listicles-agent/
├── api.py                    FastAPI backend (HTTP + SSE streaming)
├── seo_listicles_agent.py    Core agent: SERP fetch, classify, detect, export
├── database.py               SQLite layer (companies / keywords / searches / results)
├── static/
│   └── index.html            Single-page frontend (vanilla JS, no framework)
├── requirements.txt
├── .env.example              Copy to .env and add your keys
└── README.md
```

### Key files

| File | Lines | Purpose |
|---|---|---|
| `seo_listicles_agent.py` | ~1300 | Classify pages, detect domains, build Excel |
| `api.py` | ~330 | REST + SSE endpoints, request models |
| `database.py` | ~390 | SQLite schema + queries (companies, history, export) |
| `static/index.html` | ~1100 | UI: search form, history panel, companies, modals |

---

## API reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Serve the frontend |
| `/api/regions` | GET | List supported regions (US, UK, IN, …) |
| `/api/search` | POST | Start a search (returns `run_id`) |
| `/api/stream/{run_id}` | GET | SSE stream of progress + final results |
| `/api/verify-url` | POST | Diagnostic re-fetch for any URL (the 🔍 button) |
| `/api/companies` | GET / POST | List or create company profiles |
| `/api/companies/{id}` | PUT / DELETE | Edit or remove a company |
| `/api/companies/{id}/history` | GET | List all searches for a company |
| `/api/companies/{id}/export` | POST | Excel report (single or selected searches) |
| `/api/history` | GET | All searches (optionally filter by domain) |
| `/api/history/{search_id}` | DELETE | Remove one search |
| `/api/export-history` | POST | Excel export with flexible filters |
| `/api/domains` | GET | Unique searched domains (for dropdown) |

---

## How the agent handles edge cases

| Situation | Behavior |
|---|---|
| Brotli-compressed pages | Fixed by removing `br` from Accept-Encoding header |
| LinkedIn `<h3><span>1. Company</span></h3>` | Heading regex strips inner tags first |
| Page title (H1) counted as #1 | Position counter skips H1, uses dominant H2/H3 level |
| Reddit/Cloudflare scraper blocks | Detected via stub-size + verification text → "Check Manually" status |
| Company name with spaces ("WPWeb Infotech") vs domain ("wpwebinfotech") | Compact-text match (strips spaces/punctuation) finds both |
| False positives (e.g. "wpwebelite" matching "wpwebinfotech") | Word-boundary regex prevents substring matches |
| Same domain searched as "wpwebinfotech" and "wpwebinfotech.com" | Normalized at save time — treated as same company |
| Service pages with marketing titles like "Top WordPress Agency" | Classified by URL pattern (`/services/`) before title hype |
| YouTube ranking for "best WordPress dev" | Classified as **Video**, doesn't count toward listicle target |

---

## Tech stack

- **Python 3.12+**
- **FastAPI** — HTTP API + SSE
- **Uvicorn** — ASGI server
- **SQLite** — local persistence (no setup needed)
- **openpyxl** — Excel formatting (colors, merged cells, borders)
- **requests** — HTTP fetching
- **Serper.dev** — Google SERP API
- **Open PageRank** — free authority scores
- **Vanilla JS** — no frontend framework, single HTML file

---

## Known limitations

- **Reddit / Cloudflare-protected pages** return a stub HTML. Marked "Check Manually" — verify in browser.
- **JavaScript-rendered listicles** (rare in SEO content) won't have their list visible in static HTML.
- **Serper.dev SERP** is a generic-US Google view. Your personal/city-level Google may show slightly different results.
- **OPR (Open PageRank)** has limited domain coverage. Many domains return blank scores — this doesn't mean the domain is weak.

---

## Roadmap ideas

- [ ] Email contact extraction (already partially built, hidden behind checkbox)
- [ ] Scheduled re-runs (track SERP changes over time)
- [ ] Outreach email drafts per Listed page
- [ ] Slack/Discord notifications when a new ranking is detected
- [ ] CSV export option

---

## License

MIT — use it freely. PRs welcome.
