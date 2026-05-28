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

    conn.commit()
    conn.close()


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
