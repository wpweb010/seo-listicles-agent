"""
SQLite database for search history and results caching.
"""
import sqlite3
import hashlib
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "search_history.db"


def normalize_domain(domain: str) -> str:
    """Normalize domain: 'WpWebInfoTech.com' → 'wpwebinfotech.com', 'wpwebinfotech' → 'wpwebinfotech.com'."""
    if not domain:
        return ""
    d = domain.lower().strip()
    d = d.replace("http://", "").replace("https://", "")
    d = d.replace("www.", "")
    d = d.split("/")[0]  # Remove path
    # If no TLD, assume .com
    if "." not in d:
        d = d + ".com"
    return d


def init_db():
    """Create database schema if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Companies table: profiles for managing multi-domain outreach
    c.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            domain TEXT NOT NULL UNIQUE,
            name_variants TEXT,
            created_at TEXT
        )
    """)

    # Keywords table: tracks unique keyword+location combos
    c.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY,
            keyword TEXT NOT NULL,
            location TEXT DEFAULT 'us',
            serp_hash TEXT,
            timestamp TEXT,
            UNIQUE(keyword, location)
        )
    """)

    # Searches table: tracks each search (keyword + optional company)
    c.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY,
            keyword_id INTEGER NOT NULL,
            company_id INTEGER,
            domain TEXT,
            timestamp TEXT,
            result_count INTEGER,
            FOREIGN KEY(keyword_id) REFERENCES keywords(id),
            FOREIGN KEY(company_id) REFERENCES companies(id)
        )
    """)

    # Results table: individual listicle/aggregator results
    c.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY,
            search_id INTEGER NOT NULL,
            position INTEGER,
            domain TEXT,
            url TEXT,
            title TEXT,
            page_type TEXT,
            status TEXT,
            position_on_page TEXT,
            link_type TEXT,
            notes TEXT,
            FOREIGN KEY(search_id) REFERENCES searches(id)
        )
    """)

    # Aggregator domains — replaces hardcoded list, user-editable
    c.execute("""
        CREATE TABLE IF NOT EXISTS aggregator_domains (
            id INTEGER PRIMARY KEY,
            domain TEXT NOT NULL UNIQUE,
            created_at TEXT
        )
    """)

    # Video platform domains
    c.execute("""
        CREATE TABLE IF NOT EXISTS video_domains (
            id INTEGER PRIMARY KEY,
            domain TEXT NOT NULL UNIQUE,
            created_at TEXT
        )
    """)

    # API keys — user-managed, overrides .env values
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            provider TEXT PRIMARY KEY,
            api_key TEXT NOT NULL,
            extra_data TEXT,
            last_tested TEXT,
            last_status TEXT,
            usage_count INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    # API usage log — track every API call for usage reporting
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_usage_log (
            id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL,
            timestamp TEXT,
            success INTEGER DEFAULT 1,
            credits_remaining INTEGER,
            metadata TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_provider ON api_usage_log(provider)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_time ON api_usage_log(timestamp)")

    conn.commit()

    # Pre-populate aggregator_domains and video_domains on first run
    _seed_defaults(conn)

    conn.close()


# ── Default seeds (run once on fresh DB) ────────────────────────────────

DEFAULT_AGGREGATORS = [
    "clutch.co", "goodfirms.co", "g2.com", "capterra.com", "trustradius.com",
    "sortlist.com", "topdevelopers.co", "themanifest.com", "expertise.com",
    "designrush.com", "appfutura.com", "itfirms.co", "selectedfirms.co",
    "upcity.com", "gartner.com", "forrester.com",
    "trustpilot.com", "yelp.com", "yellowpages.com", "bbb.org",
    "glassdoor.com", "ambitionbox.com",
    "techreviewer.co", "crowdreviews.com", "businessofapps.com",
    "softwareworld.co", "mobileappdaily.com", "10seos.com",
    "indiamart.com", "alibaba.com", "upwork.com", "fiverr.com",
    "freelancer.com", "guru.com", "toptal.com", "gun.io",
    "stackoverflow.com", "github.com", "producthunt.com",
]

DEFAULT_VIDEOS = [
    "youtube.com", "youtu.be", "vimeo.com", "tiktok.com",
    "dailymotion.com", "twitch.tv", "rumble.com",
]


def _seed_defaults(conn):
    """Insert default aggregators and video domains if the tables are empty."""
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM aggregator_domains")
    if c.fetchone()[0] == 0:
        for d in DEFAULT_AGGREGATORS:
            c.execute(
                "INSERT OR IGNORE INTO aggregator_domains (domain, created_at) VALUES (?, ?)",
                (d, datetime.now().isoformat())
            )
    c.execute("SELECT COUNT(*) FROM video_domains")
    if c.fetchone()[0] == 0:
        for d in DEFAULT_VIDEOS:
            c.execute(
                "INSERT OR IGNORE INTO video_domains (domain, created_at) VALUES (?, ?)",
                (d, datetime.now().isoformat())
            )
    conn.commit()


# ── Aggregator domains CRUD ──────────────────────────────────────────────

def get_aggregator_domains() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, domain, created_at FROM aggregator_domains ORDER BY domain")
    rows = [{"id": r[0], "domain": r[1], "created_at": r[2]} for r in c.fetchall()]
    conn.close()
    return rows


def get_aggregator_domain_list() -> list:
    """Just the list of domain strings (for classify())."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT domain FROM aggregator_domains")
    out = [r[0] for r in c.fetchall()]
    conn.close()
    return out


def add_aggregator_domain(domain: str) -> int:
    d = normalize_domain(domain)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO aggregator_domains (domain, created_at) VALUES (?, ?)",
            (d, datetime.now().isoformat())
        )
        conn.commit()
        return c.lastrowid
    except sqlite3.IntegrityError:
        c.execute("SELECT id FROM aggregator_domains WHERE domain = ?", (d,))
        row = c.fetchone()
        return row[0] if row else -1
    finally:
        conn.close()


def delete_aggregator_domain(domain_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM aggregator_domains WHERE id = ?", (domain_id,))
    conn.commit()
    conn.close()


# ── Video domains CRUD ───────────────────────────────────────────────────

def get_video_domains() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, domain, created_at FROM video_domains ORDER BY domain")
    rows = [{"id": r[0], "domain": r[1], "created_at": r[2]} for r in c.fetchall()]
    conn.close()
    return rows


def get_video_domain_list() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT domain FROM video_domains")
    out = [r[0] for r in c.fetchall()]
    conn.close()
    return out


def add_video_domain(domain: str) -> int:
    d = normalize_domain(domain)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO video_domains (domain, created_at) VALUES (?, ?)",
            (d, datetime.now().isoformat())
        )
        conn.commit()
        return c.lastrowid
    except sqlite3.IntegrityError:
        c.execute("SELECT id FROM video_domains WHERE domain = ?", (d,))
        row = c.fetchone()
        return row[0] if row else -1
    finally:
        conn.close()


def delete_video_domain(domain_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM video_domains WHERE id = ?", (domain_id,))
    conn.commit()
    conn.close()


# ── API keys CRUD ────────────────────────────────────────────────────────

def get_api_keys() -> list:
    """List all stored API keys (masked for display)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM api_keys ORDER BY provider")
    out = []
    for row in c.fetchall():
        d = dict(row)
        d["extra_data"] = json.loads(d["extra_data"] or "{}")
        # Masked display version
        key = d["api_key"] or ""
        d["key_masked"] = key[:4] + "•" * 12 + key[-4:] if len(key) > 8 else "•" * len(key)
        out.append(d)
    conn.close()
    return out


def get_api_key(provider: str) -> dict:
    """Get a single api key entry (full, for backend use). Returns None if missing."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM api_keys WHERE provider = ?", (provider,))
    row = c.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["extra_data"] = json.loads(d["extra_data"] or "{}")
        return d
    return None


def upsert_api_key(provider: str, api_key: str, extra_data: dict = None):
    """Add or update an API key."""
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT provider FROM api_keys WHERE provider = ?", (provider,))
    if c.fetchone():
        c.execute("""UPDATE api_keys SET api_key = ?, extra_data = ?, updated_at = ?
                     WHERE provider = ?""",
                  (api_key, json.dumps(extra_data or {}), now, provider))
    else:
        c.execute("""INSERT INTO api_keys (provider, api_key, extra_data, created_at, updated_at)
                     VALUES (?, ?, ?, ?, ?)""",
                  (provider, api_key, json.dumps(extra_data or {}), now, now))
    conn.commit()
    conn.close()


def delete_api_key(provider: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM api_keys WHERE provider = ?", (provider,))
    conn.commit()
    conn.close()


def set_api_key_status(provider: str, status: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE api_keys SET last_tested = ?, last_status = ? WHERE provider = ?",
              (datetime.now().isoformat(), status, provider))
    conn.commit()
    conn.close()


def log_api_call(provider: str, success: bool = True, credits_remaining: int = None, metadata: dict = None):
    """Record an API call for usage tracking."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO api_usage_log (provider, timestamp, success, credits_remaining, metadata)
                 VALUES (?, ?, ?, ?, ?)""",
              (provider, datetime.now().isoformat(), 1 if success else 0,
               credits_remaining, json.dumps(metadata or {})))
    c.execute("UPDATE api_keys SET usage_count = usage_count + 1 WHERE provider = ?", (provider,))
    conn.commit()
    conn.close()


def get_api_usage(provider: str = None) -> dict:
    """Aggregated usage stats. If provider given, returns single. Else dict of all."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if provider:
        c.execute("""SELECT COUNT(*), MAX(credits_remaining), MAX(timestamp)
                     FROM api_usage_log WHERE provider = ?""", (provider,))
        total, latest_credits, last_call = c.fetchone()
        # Today
        from datetime import datetime as dt
        today_start = dt.now().strftime("%Y-%m-%d")
        c.execute("""SELECT COUNT(*) FROM api_usage_log
                     WHERE provider = ? AND timestamp >= ?""", (provider, today_start))
        today = c.fetchone()[0]
        conn.close()
        return {
            "provider": provider, "total_calls": total or 0,
            "today_calls": today or 0,
            "latest_credits": latest_credits,
            "last_call": last_call,
        }
    # All providers
    c.execute("SELECT DISTINCT provider FROM api_usage_log")
    providers = [r[0] for r in c.fetchall()]
    conn.close()
    return {p: get_api_usage(p) for p in providers}


# ── Dashboard aggregations ───────────────────────────────────────────────

def get_dashboard_stats() -> dict:
    """Aggregated stats for dashboard display."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM companies")
    company_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM searches")
    search_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM keywords")
    keyword_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM results")
    result_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM results WHERE status = 'Listed'")
    listed_count = c.fetchone()[0]

    # Per-company stats
    c.execute("""
        SELECT c.id, c.name, c.domain,
               COUNT(DISTINCT s.id) as searches,
               COUNT(r.id) as total_results,
               SUM(CASE WHEN r.status = 'Listed' THEN 1 ELSE 0 END) as listed
        FROM companies c
        LEFT JOIN searches s ON s.company_id = c.id
        LEFT JOIN results r ON r.search_id = s.id
        GROUP BY c.id
        ORDER BY listed DESC, searches DESC
    """)
    company_stats = []
    for row in c.fetchall():
        avg_pos = None
        c.execute("""SELECT AVG(CAST(position_on_page AS REAL))
                     FROM results r JOIN searches s ON r.search_id = s.id
                     WHERE s.company_id = ? AND r.status = 'Listed'
                     AND position_on_page GLOB '[0-9]*'""", (row[0],))
        avg = c.fetchone()[0]
        if avg is not None:
            avg_pos = round(avg, 1)
        company_stats.append({
            "id": row[0], "name": row[1], "domain": row[2],
            "searches": row[3] or 0,
            "total_results": row[4] or 0,
            "listed": row[5] or 0,
            "avg_position": avg_pos,
        })

    # Activity over last 30 days
    c.execute("""
        SELECT DATE(timestamp) as day, COUNT(*) as count
        FROM searches
        WHERE timestamp >= DATE('now', '-30 days')
        GROUP BY day ORDER BY day
    """)
    activity = [{"date": r[0], "count": r[1]} for r in c.fetchall()]

    # Recent searches
    c.execute("""
        SELECT s.id, k.keyword, k.location, c.name, s.timestamp, s.result_count
        FROM searches s
        JOIN keywords k ON s.keyword_id = k.id
        LEFT JOIN companies c ON s.company_id = c.id
        ORDER BY s.timestamp DESC LIMIT 8
    """)
    recent = []
    for row in c.fetchall():
        recent.append({
            "search_id": row[0], "keyword": row[1], "location": row[2],
            "company": row[3] or "(no company)", "timestamp": row[4],
            "result_count": row[5] or 0,
        })

    conn.close()
    return {
        "totals": {
            "companies": company_count, "searches": search_count,
            "keywords": keyword_count, "results": result_count,
            "listed": listed_count,
        },
        "company_stats": company_stats,
        "activity_30d": activity,
        "recent_searches": recent,
    }


def get_cached_search_results(search_id: int) -> list:
    """Load cached results for a past search (no API call needed)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT r.position, r.domain, r.url, r.title, r.page_type,
               r.status, r.position_on_page, r.link_type, r.notes,
               k.keyword, k.location, s.domain as searched_domain
        FROM results r
        JOIN searches s ON r.search_id = s.id
        JOIN keywords k ON s.keyword_id = k.id
        WHERE r.search_id = ?
        ORDER BY r.position
    """, (search_id,))
    rows = []
    for row in c.fetchall():
        d = dict(row)
        rows.append({
            "Position": d["position"],
            "Domain": d["domain"],
            "URL": d["url"],
            "Title": d.get("title", ""),
            "Page Type": d["page_type"],
            "Listicle Target?": "YES" if (d["page_type"] or "").startswith("Listicle") else "NO",
            "Authority Score": "",
            "Priority Score": 0,
            "Keyword Density %": "",
            "Live?": True if d["status"] else "",
            "Has List Content?": "",
            "Validated?": True if d["status"] == "Listed" else "",
            "Email": "", "Submit URL": "", "Contact URL": "",
            "Status": d.get("status", "") or "",
            "Position on Page": d.get("position_on_page", "") or "",
            "Link Type": d.get("link_type", "") or "",
            "Notes": d.get("notes", "") or "",
            "Category": "listicle" if (d["page_type"] or "").startswith("Listicle") else
                        "aggregator" if d["page_type"] == "Aggregator" else
                        "service_page" if d["page_type"] == "Service Page" else
                        "video" if d["page_type"] == "Video" else "other",
            "_keyword": d["keyword"],
            "_location": d["location"],
        })
    conn.close()
    return rows


def get_startup_info() -> dict:
    """Return DB stats for startup log."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    out = {}
    for table in ("companies", "keywords", "searches", "results",
                  "aggregator_domains", "video_domains", "api_keys"):
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            out[table] = c.fetchone()[0]
        except sqlite3.OperationalError:
            out[table] = 0
    conn.close()
    return out


# ── Company management ───────────────────────────────────────────────────

def _auto_variants(name: str, domain: str) -> list:
    """Auto-generate search variants from name + domain."""
    variants = set()
    if domain:
        d = normalize_domain(domain)
        short = d.split(".")[0]
        variants.add(d)
        variants.add(short)
    if name:
        variants.add(name)
        variants.add(name.lower())
        variants.add(name.upper())
        variants.add(name.replace(" ", ""))
    return sorted(v for v in variants if v)


def create_company(name: str, domain: str, custom_variants: list = None) -> int:
    """Create a company profile. Returns company id."""
    domain_norm = normalize_domain(domain)
    auto = _auto_variants(name, domain_norm)
    if custom_variants:
        auto = sorted(set(auto + [v.strip() for v in custom_variants if v.strip()]))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO companies (name, domain, name_variants, created_at) VALUES (?, ?, ?, ?)",
            (name, domain_norm, json.dumps(auto), datetime.now().isoformat())
        )
        conn.commit()
        company_id = c.lastrowid
    except sqlite3.IntegrityError:
        c.execute("SELECT id FROM companies WHERE domain = ?", (domain_norm,))
        company_id = c.fetchone()[0]
    conn.close()
    return company_id


def update_company(company_id: int, name: str = None, custom_variants: list = None):
    """Update a company's name or variants."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if name is not None:
        c.execute("UPDATE companies SET name = ? WHERE id = ?", (name, company_id))
    if custom_variants is not None:
        c.execute("SELECT name, domain FROM companies WHERE id = ?", (company_id,))
        row = c.fetchone()
        if row:
            auto = _auto_variants(row[0], row[1])
            merged = sorted(set(auto + [v.strip() for v in custom_variants if v.strip()]))
            c.execute("UPDATE companies SET name_variants = ? WHERE id = ?",
                      (json.dumps(merged), company_id))
    conn.commit()
    conn.close()


def delete_company(company_id: int):
    """Delete a company and unlink its searches."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE searches SET company_id = NULL WHERE company_id = ?", (company_id,))
    c.execute("DELETE FROM companies WHERE id = ?", (company_id,))
    conn.commit()
    conn.close()


def get_companies() -> list:
    """Get all companies with search counts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT c.id, c.name, c.domain, c.name_variants, c.created_at,
               COUNT(s.id) as search_count
        FROM companies c
        LEFT JOIN searches s ON s.company_id = c.id
        GROUP BY c.id
        ORDER BY c.name
    """)
    out = []
    for row in c.fetchall():
        d = dict(row)
        d["name_variants"] = json.loads(d["name_variants"] or "[]")
        out.append(d)
    conn.close()
    return out


def get_company_by_domain(domain: str):
    """Find company by normalized domain."""
    if not domain:
        return None
    domain_norm = normalize_domain(domain)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM companies WHERE domain = ?", (domain_norm,))
    row = c.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["name_variants"] = json.loads(d["name_variants"] or "[]")
        return d
    return None


def get_company(company_id: int):
    """Get one company by id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
    row = c.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["name_variants"] = json.loads(d["name_variants"] or "[]")
        return d
    return None


def get_serp_hash(serp_results: list) -> str:
    """Generate hash from SERP results to detect changes."""
    urls = [r.get("url", "") for r in serp_results]
    hash_input = "|".join(urls)
    return hashlib.md5(hash_input.encode()).hexdigest()


def find_keyword(keyword: str, region: str = "us"):
    """Find if keyword was previously searched."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, serp_hash FROM keywords WHERE keyword = ? AND location = ?",
        (keyword, region)
    )
    result = c.fetchone()
    conn.close()
    return result


def save_keyword(keyword: str, region: str, serp_hash: str):
    """Save or update keyword with SERP hash."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO keywords (keyword, location, serp_hash, timestamp) "
        "VALUES (?, ?, ?, ?)",
        (keyword, region, serp_hash, datetime.now().isoformat())
    )
    conn.commit()
    keyword_id = c.lastrowid
    conn.close()
    return keyword_id


def save_search(keyword_id: int, domain: str, result_count: int, company_id: int = None) -> int:
    """Save a search record. Auto-links to company by domain if company_id not given."""
    normalized = normalize_domain(domain) if domain else None

    # Auto-link to company by domain if not specified
    if normalized and company_id is None:
        company = get_company_by_domain(normalized)
        if company:
            company_id = company["id"]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO searches (keyword_id, company_id, domain, timestamp, result_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (keyword_id, company_id, normalized, datetime.now().isoformat(), result_count)
    )
    conn.commit()
    search_id = c.lastrowid
    conn.close()
    return search_id


def save_results(search_id: int, results: list):
    """Save result rows to database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for r in results:
        c.execute("""
            INSERT INTO results
            (search_id, position, domain, url, title, page_type, status, position_on_page, link_type, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            search_id,
            r.get("Position"),
            r.get("Domain"),
            r.get("URL"),
            r.get("Title", ""),
            r.get("Page Type"),
            r.get("Status", ""),
            r.get("Position on Page", ""),
            r.get("Link Type", ""),
            r.get("Notes", "")
        ))
    conn.commit()
    conn.close()


def get_history_by_company(company_id: int):
    """Get all searches for a specific company."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT s.id as search_id, k.id as keyword_id,
               k.keyword, k.location, s.domain,
               COUNT(r.id) as result_count, s.timestamp
        FROM searches s
        JOIN keywords k ON s.keyword_id = k.id
        LEFT JOIN results r ON s.id = r.search_id
        WHERE s.company_id = ?
        GROUP BY s.id
        ORDER BY s.timestamp DESC
    """, (company_id,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_results_by_company(company_id: int, search_ids: list = None):
    """Get all results for a company, optionally filtered by specific search IDs."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = """
        SELECT k.keyword, k.location, s.domain as searched_domain,
               r.position, r.domain as page_domain, r.url, r.title, r.page_type,
               r.status, r.position_on_page, r.link_type, r.notes
        FROM results r
        JOIN searches s ON r.search_id = s.id
        JOIN keywords k ON s.keyword_id = k.id
        WHERE s.company_id = ?
    """
    params = [company_id]

    if search_ids:
        placeholders = ",".join("?" * len(search_ids))
        query += f" AND s.id IN ({placeholders})"
        params.extend(search_ids)

    query += """
        AND (r.page_type LIKE 'Listicle%' OR r.page_type = 'Aggregator'
             OR r.page_type = 'Service Page' OR r.page_type = 'Blog / Article'
             OR r.page_type = 'Possible listicle' OR r.page_type = 'Video')
        ORDER BY k.keyword, k.location, r.position
    """

    c.execute(query, params)
    rows = []
    for row in c.fetchall():
        d = dict(row)
        rows.append({
            "Keyword": d["keyword"],
            "Location": d["location"],
            "Position": d["position"],
            "Domain": d["page_domain"],
            "URL": d["url"],
            "Title": d.get("title", ""),
            "Page Type": d["page_type"],
            "Status": d.get("status", ""),
            "Position on Page": d.get("position_on_page", ""),
            "Link Type": d.get("link_type", ""),
            "Notes": d.get("notes", ""),
            "Searched Domain": d.get("searched_domain", ""),
        })
    conn.close()
    return rows


def get_history(domain: str = None):
    """Get search history, optionally filtered by domain."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if domain == "__none__":
        c.execute("""
            SELECT s.id as search_id, k.id as keyword_id,
                   k.keyword, k.location, s.domain,
                   COUNT(r.id) as result_count, s.timestamp
            FROM searches s
            JOIN keywords k ON s.keyword_id = k.id
            LEFT JOIN results r ON s.id = r.search_id
            WHERE s.domain IS NULL OR s.domain = ''
            GROUP BY s.id
            ORDER BY s.timestamp DESC
        """)
    elif domain:
        normalized = normalize_domain(domain)
        c.execute("""
            SELECT s.id as search_id, k.id as keyword_id,
                   k.keyword, k.location, s.domain,
                   COUNT(r.id) as result_count, s.timestamp
            FROM searches s
            JOIN keywords k ON s.keyword_id = k.id
            LEFT JOIN results r ON s.id = r.search_id
            WHERE s.domain = ?
            GROUP BY s.id
            ORDER BY s.timestamp DESC
        """, (normalized,))
    else:
        c.execute("""
            SELECT s.id as search_id, k.id as keyword_id,
                   k.keyword, k.location, s.domain,
                   COUNT(r.id) as result_count, s.timestamp
            FROM searches s
            JOIN keywords k ON s.keyword_id = k.id
            LEFT JOIN results r ON s.id = r.search_id
            GROUP BY s.id
            ORDER BY s.timestamp DESC
        """)

    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_results_for_export(search_ids: list = None, domain_filter: str = None):
    """
    Get results for export with optional filters.
    search_ids: list of search IDs to export (None = all)
    domain_filter: None (all), "__none__" (no domain only), or specific domain name.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = """
        SELECT
            k.keyword, k.location,
            s.domain as searched_domain,
            r.position, r.domain as page_domain, r.url, r.title, r.page_type,
            r.status, r.position_on_page, r.link_type, r.notes
        FROM results r
        JOIN searches s ON r.search_id = s.id
        JOIN keywords k ON s.keyword_id = k.id
        WHERE 1=1
    """
    params = []

    if search_ids:
        placeholders = ",".join("?" * len(search_ids))
        query += f" AND s.id IN ({placeholders})"
        params.extend(search_ids)

    if domain_filter is not None:
        if domain_filter == "__none__":
            query += " AND (s.domain IS NULL OR s.domain = '')"
        elif domain_filter:
            query += " AND s.domain = ?"
            params.append(normalize_domain(domain_filter))

    # Only include the 3 target categories: Listicles, Service Pages, Aggregators
    query += """
        AND (r.page_type LIKE 'Listicle%' OR r.page_type = 'Aggregator'
             OR r.page_type = 'Service Page' OR r.page_type = 'Blog / Article'
             OR r.page_type = 'Possible listicle' OR r.page_type = 'Video')
    """
    query += " ORDER BY k.keyword, k.location, r.position"

    c.execute(query, params)
    rows = []
    for row in c.fetchall():
        d = dict(row)
        # Transform to match write_excel expected format
        rows.append({
            "Keyword": d["keyword"],
            "Location": d["location"],
            "Position": d["position"],
            "Domain": d["page_domain"],
            "URL": d["url"],
            "Title": d.get("title", ""),
            "Page Type": d["page_type"],
            "Status": d.get("status", ""),
            "Position on Page": d.get("position_on_page", ""),
            "Link Type": d.get("link_type", ""),
            "Notes": d.get("notes", ""),
            "Searched Domain": d.get("searched_domain", ""),
        })
    conn.close()
    return rows


def get_domains_in_history():
    """Get list of unique domains searched."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT domain FROM searches WHERE domain IS NOT NULL AND domain != '' ORDER BY domain")
    domains = [row[0] for row in c.fetchall()]
    conn.close()
    return domains


def delete_search(search_id: int):
    """Delete a specific search and its results."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM results WHERE search_id = ?", (search_id,))
    c.execute("DELETE FROM searches WHERE id = ?", (search_id,))
    conn.commit()
    conn.close()


def clear_all_history():
    """Wipe all history data."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM results")
    c.execute("DELETE FROM searches")
    c.execute("DELETE FROM keywords")
    conn.commit()
    conn.close()
