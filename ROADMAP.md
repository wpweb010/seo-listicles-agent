# SEO Listicles Agent — Roadmap & Enhancement Ideas

A running list of features under consideration, captured during planning discussions.
Items are ordered by approximate impact/effort ratio.

---

## 🟢 Highest-Value Next Pick

### 1. Domain Keyword Atlas

**The pitch:** Enter any domain (competitor, prospect, partner) → see every keyword they rank for across US/UK/IN in a single wide-format table → click any keyword to find listicles for it.

**How it works:**
- New sidebar tab: 🔍 Domain Intelligence
- Input box: enter any domain
- Calls Semrush `domain_organic` 3 times (US + UK + IN = 30 units)
- Returns wide table: Keyword | US Pos | UK Pos | IN Pos | Search Volume | Action
- "🔍 Search" button per keyword → runs Serper → finds listicles for it
- 30-day cache prevents re-spending on same domain

**Use cases:**
- Competitor intelligence: "What's wisdmlabs ranking for that I'm not?"
- Outreach research: "What keywords does my prospect's website rank for?"
- Partnership discovery: "Who ranks for keywords I want to dominate?"

**Cost at scale:** 50,000 Semrush units / 30 per domain = ~1,600 domains/month.

---

## 🟡 Quick Wins (Each < 1 hour)

### 2. Outreach Status Tracking

Per listicle row, an editable status dropdown:
`Not Contacted / Sent / Replied / Listed / Declined / Follow up`

Plus a notes column for context. Persists in DB.
Filter History/Search by outreach status.

**Why valuable:** Today you find listicles but lose track of who you've contacted. This is your actual pipeline.

### 3. Email Contact Extraction (already half-built)

The `detect_email` function in `seo_listicles_agent.py` is already implemented but hidden behind a checkbox. Surface it:
- Auto-extract emails on every validated listicle
- Display in a column with mailto: link
- Look for editor@, content@, hello@, info@, contact@ prefixes
- Fall back to scraping `/contact` page

**Why valuable:** Saves the manual hunt for "who do I email about getting listed here?"

### 4. Keyword Variation Generator

Type a base keyword → auto-generate 8-10 variations:
- `"Top X companies"` → `Best X agencies` / `Hire X` / `X services` / `X for hire` / etc.
- Use Semrush `phrase_related` (40 units) OR a simple template engine

**Why valuable:** Catches listicles that rank for variants without you brainstorming.

### 5. CSV Import

Bulk-import:
- Competitor domains
- Keywords to search
- Companies

Format: simple CSV with one item per line.

**Why valuable:** Bulk setup instead of one-by-one click-through.

---

## 🟠 Bigger Wins (1-3 hours each)

### 6. Backlink Watcher

Weekly automatic re-check of pages marked "Listed with Backlink".
If a backlink disappears → alert in dashboard:
> ⚠ Lost Backlink Alert: cloudways.com no longer links to wpwebinfotech.com

**Why valuable:** Catches lost backlinks (huge for SEO). Currently you'd never know.

**Implementation:** Background job (cron-like or APScheduler). Track `last_verified_at` per Listed result. Re-fetch every 7 days. Diff vs stored detection.

### 7. Outreach Pipeline Dashboard

Kanban-style view:
```
Not Contacted (47)  →  Sent (12)  →  Replied (5)  →  Listed (2)
```
Drag-and-drop to update status. Per-card notes, dates, next-action reminders.

**Why valuable:** Visual pipeline = better follow-through.

### 8. PDF Report Generator

Per-company PDF reports with:
- Executive summary (stats, top opportunities)
- Coverage gap analysis
- Outreach pipeline status
- Priority-ranked listicle hit-list

**Why valuable:** Shareable with team / client deliverable.

### 9. Position Trend Tracking

Periodically (weekly?) re-run searches → store position history → show line charts of where you/competitors rank over time. Alert on big movements.

**Why valuable:** Long-term SEO insight + reactive alerts.

---

## 🔴 Game-Changers (3-5 hours each)

### 10. AI Email Draft Generator (Claude API)

For each "Not Contacted" listicle, generate a personalized outreach email:
- Extracts page topic + listicle pattern
- Uses Claude API to draft a custom email
- Mentions the user's company, the specific listicle, and a value prop
- User reviews + edits before sending
- Template variants per outreach style (warm / direct / collaborative)

**Why valuable:** Massive time saver. Bottleneck right now = writing emails.

**Cost:** Claude Sonnet ~$3 per 1M tokens. Each draft ~300 tokens output = $0.001 per draft.

### 11. Multi-User / Team Mode

Invite teammates → assign listicles to people → comment threads per outreach.

**Why valuable:** If scaling beyond solo operation.

**Implementation effort:** Substantial — requires auth, permissions, real-time sync.

---

## 🌐 Global Expansion

### 12. Additional Regions

Current: US, UK, CA, AU, IN, DE, FR, SG, AE.

Potential additions for global business:
- **MX** (Mexico) — LATAM gateway
- **BR** (Brazil) — large outsourcing market
- **ES** (Spain) — Spanish-speaking world entry
- **JP** (Japan) — premium market
- **KR** (Korea) — premium market

For each: add to `REGION_MAP` + UULE encoding + Semrush DB code.

### 13. Per-Company Target Regions

Currently regions are picked per-search.
Future: each company has its own default target regions (WPWeb = US+UK+IN; BrainSpate = US+IN+DE).
"Find Everything" automatically uses the company's region set.

---

## 🧹 Tech Debt & Polish

### Cleanup tasks
- Consolidate cross-verify, compare, and verify modals into one consistent UX
- Add API rate-limiting / backoff logic for Serper/Semrush
- DB backup/restore button in Settings
- Per-search "lock from auto-rerun" flag to preserve baseline snapshots
- Export config as JSON (companies, aggregators, API keys placeholder) for backup
- Improve error messages when API keys are missing (link to Settings)

### Architecture
- Move from SQLite to PostgreSQL when DB grows past 1GB
- Add Redis cache for hot-path queries (competitor lookups, dashboard stats)
- Replace polling-based spend tracker with WebSocket
- Containerize for easier deployment (Docker)

---

## 💡 Wild Ideas (Untested)

- **Slack/Discord webhook** — notify on new rankings, lost backlinks, replies received
- **Mobile companion app** — review outreach pipeline on phone, approve drafts
- **Browser extension** — when browsing a competitor's site, instantly see "Mine keywords" button
- **Voice control** — "Hey agent, find new WordPress listicles for me" (probably overkill)
- **Integration with HubSpot/Pipedrive CRM** — push outreach activity into existing CRM

---

## How to use this file

Items here are NOT committed to. Pick the one(s) that match your current need.
Discussion happens in the chat, decisions get added here, work gets tracked in TaskList.

When picking, consider:
- **Impact:** Does this unlock new revenue or save real time?
- **Effort:** Honest time estimate
- **Dependencies:** Does it need another feature first?
- **Reversibility:** Can we ship behind a feature flag?
