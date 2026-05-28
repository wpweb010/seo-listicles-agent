"""
Phase 5 endpoints — Dashboard, Settings, Power Features.
Imported and registered onto the main app in api.py.
"""

from fastapi import HTTPException
from pydantic import BaseModel
import requests as _http


# ── Pydantic models ──────────────────────────────────────────────────────

class AggregatorRequest(BaseModel):
    domain: str


class VideoDomainRequest(BaseModel):
    domain: str


class ApiKeyRequest(BaseModel):
    provider:      str
    api_key:       str
    label:         str | None  = None
    priority:      int         = 0
    monthly_limit: int | None  = None
    daily_limit:   int | None  = None
    extra_data:    dict | None = None


class ApiKeyUpdateRequest(BaseModel):
    label:         str | None  = None
    priority:      int | None  = None
    is_active:     bool | None = None
    monthly_limit: int | None  = None
    daily_limit:   int | None  = None
    extra_data:    dict | None = None


class BulkSearchRequest(BaseModel):
    keywords:         list[str]
    company_id:       int | None = None
    domain:           str         = ""
    region:           str         = "us"
    target_listicles: int         = 10
    max_pages:        int         = 20
    mode:             str         = "free"


# ── API key validation helpers ───────────────────────────────────────────

def test_serper_key(api_key: str) -> dict:
    """Test a Serper.dev API key by making a single small query."""
    try:
        r = _http.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": "test", "gl": "us", "hl": "en", "num": 1},
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            return {"ok": False, "message": str(data.get("error"))}
        credits = data.get("credits") or data.get("credits_remaining")
        return {"ok": True, "message": "Connected successfully",
                "credits": credits, "raw_status": r.status_code}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def test_google_cse(api_key: str, cx: str) -> dict:
    """Test Google CSE key + cx."""
    if not cx:
        return {"ok": False, "message": "Search Engine ID (cx) is required"}
    try:
        r = _http.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": api_key, "cx": cx, "q": "test", "num": 1},
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            return {"ok": False, "message": data["error"].get("message", "Unknown error")}
        return {"ok": True, "message": "Connected successfully",
                "raw_status": r.status_code}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def test_openpagerank(api_key: str) -> dict:
    """Test Open PageRank key."""
    try:
        r = _http.get(
            "https://openpagerank.com/api/v1.0/getPageRank",
            params=[("domains[]", "google.com")],
            headers={"API-OPR": api_key},
            timeout=10,
        )
        data = r.json()
        if data.get("status_code") and data["status_code"] != 200:
            return {"ok": False, "message": str(data.get("message", "Unknown error"))}
        # Successful response has a 'response' array
        if "response" in data:
            return {"ok": True, "message": "Connected successfully",
                    "raw_status": r.status_code}
        return {"ok": False, "message": "Unexpected response format"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def test_semrush(api_key: str) -> dict:
    """Test Semrush by querying domain_ranks for google.com."""
    try:
        r = _http.get(
            "https://api.semrush.com/",
            params={"type": "domain_ranks", "key": api_key,
                    "domain": "google.com", "database": "us",
                    "export_columns": "Dn,Sh"},
            timeout=10,
        )
        text = r.text.strip()
        if text.startswith("ERROR"):
            return {"ok": False, "message": text}
        if ";" in text:
            return {"ok": True, "message": "Connected successfully",
                    "raw_status": r.status_code}
        return {"ok": False, "message": "Unexpected response"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


KEY_TESTERS = {
    "serper":       lambda key, extra: test_serper_key(key),
    "google_cse":   lambda key, extra: test_google_cse(key, (extra or {}).get("cx", "")),
    "openpagerank": lambda key, extra: test_openpagerank(key),
    "semrush":      lambda key, extra: test_semrush(key),
}


def register_routes(app, agent, database):
    """Attach all phase-5 endpoints to the FastAPI app."""

    # ── Dashboard ────────────────────────────────────────────────────────

    @app.get("/api/dashboard")
    async def dashboard_stats():
        return database.get_dashboard_stats()

    # ── Aggregator domains ──────────────────────────────────────────────

    @app.get("/api/aggregators")
    async def list_aggregators():
        return {"aggregators": database.get_aggregator_domains()}

    @app.post("/api/aggregators")
    async def add_aggregator(req: AggregatorRequest):
        if not req.domain.strip():
            raise HTTPException(400, "Domain required")
        agg_id = database.add_aggregator_domain(req.domain.strip())
        return {"id": agg_id, "domain": database.normalize_domain(req.domain.strip())}

    @app.delete("/api/aggregators/{agg_id}")
    async def remove_aggregator(agg_id: int):
        database.delete_aggregator_domain(agg_id)
        return {"status": "deleted"}

    # ── Video domains ───────────────────────────────────────────────────

    @app.get("/api/video-domains")
    async def list_videos():
        return {"videos": database.get_video_domains()}

    @app.post("/api/video-domains")
    async def add_video(req: VideoDomainRequest):
        if not req.domain.strip():
            raise HTTPException(400, "Domain required")
        vid = database.add_video_domain(req.domain.strip())
        return {"id": vid, "domain": database.normalize_domain(req.domain.strip())}

    @app.delete("/api/video-domains/{vid}")
    async def remove_video(vid: int):
        database.delete_video_domain(vid)
        return {"status": "deleted"}

    # ── API key management (multi-key per provider) ────────────────────

    @app.get("/api/api-keys")
    async def list_api_keys():
        """List ALL API keys (multiple per provider supported)."""
        return {"keys": database.get_api_keys()}

    @app.post("/api/api-keys")
    async def save_api_key(req: ApiKeyRequest):
        """Add a NEW API key (allows multiple keys per provider)."""
        provider = req.provider.strip().lower()
        if provider not in KEY_TESTERS:
            raise HTTPException(400, f"Unknown provider: {req.provider}")
        if not req.api_key.strip():
            raise HTTPException(400, "API key cannot be empty")
        key_id = database.add_api_key(
            provider, req.api_key.strip(),
            label=req.label, priority=req.priority,
            monthly_limit=req.monthly_limit, daily_limit=req.daily_limit,
            extra_data=req.extra_data or {},
        )
        return {"status": "saved", "id": key_id, "provider": provider}

    @app.put("/api/api-keys/id/{key_id}")
    async def update_api_key_endpoint(key_id: int, req: ApiKeyUpdateRequest):
        """Update label/priority/active/quota on an existing key."""
        database.update_api_key(
            key_id, label=req.label, priority=req.priority,
            is_active=req.is_active, monthly_limit=req.monthly_limit,
            daily_limit=req.daily_limit, extra_data=req.extra_data,
        )
        return {"status": "updated", "id": key_id}

    @app.delete("/api/api-keys/id/{key_id}")
    async def delete_api_key_by_id_endpoint(key_id: int):
        """Delete one specific key by its ID."""
        database.delete_api_key(int(key_id))
        return {"status": "deleted", "id": key_id}

    @app.post("/api/api-keys/id/{key_id}/test")
    async def test_api_key_by_id(key_id: int):
        """Test a specific key by ID."""
        # Find the key
        keys = database.get_api_keys()
        match = next((k for k in keys if k["id"] == key_id), None)
        if not match:
            raise HTTPException(404, "Key not found")
        provider = match["provider"]
        if provider not in KEY_TESTERS:
            raise HTTPException(400, f"Unknown provider: {provider}")
        result = KEY_TESTERS[provider](match["api_key"], match.get("extra_data"))
        database.set_api_key_status(key_id, "ok" if result["ok"] else "error")
        return result

    @app.delete("/api/api-keys/{provider}")
    async def remove_api_key_legacy(provider: str):
        """Legacy: delete ALL keys for a provider."""
        database.delete_api_key(provider.lower())
        return {"status": "deleted"}

    @app.post("/api/api-keys/{provider}/test")
    async def test_api_key_legacy(provider: str):
        """Legacy: test the active/primary key for a provider."""
        provider = provider.lower()
        if provider not in KEY_TESTERS:
            raise HTTPException(400, f"Unknown provider: {provider}")
        key_row = database.get_active_api_key(provider)
        if not key_row:
            raise HTTPException(404, "API key not saved")
        result = KEY_TESTERS[provider](key_row["api_key"], key_row.get("extra_data"))
        database.set_api_key_status(key_row["id"], "ok" if result["ok"] else "error")
        return result

    @app.get("/api/api-keys/usage")
    async def api_usage_overall():
        return {"usage": database.get_api_usage()}

    # ── Competitor intelligence (listicle co-occurrence) ───────────────

    @app.get("/api/companies/{company_id}/keywords")
    async def get_company_keywords(company_id: int):
        """All keywords searched under a company (for filter dropdown)."""
        company = database.get_company(company_id)
        if not company:
            raise HTTPException(404, "Company not found")
        return {
            "company": {"id": company["id"], "name": company["name"], "domain": company["domain"]},
            "keywords": database.get_keywords_for_company(company_id),
        }

    @app.get("/api/competitors/{company_id}")
    async def get_competitors(company_id: int, min_appearances: int = 2, keyword_ids: str = ""):
        """
        Auto-discovered competitors for a company.
        Optional ?keyword_ids=1,2,3 to filter by specific keywords.
        """
        company = database.get_company(company_id)
        if not company:
            raise HTTPException(404, "Company not found")

        kw_ids = None
        if keyword_ids:
            try:
                kw_ids = [int(x) for x in keyword_ids.split(",") if x.strip()]
            except ValueError:
                raise HTTPException(400, "keyword_ids must be comma-separated integers")

        competitors = database.get_competitors_for_company(
            company_id, min_appearances=min_appearances, keyword_ids=kw_ids,
        )
        return {
            "company": {"id": company["id"], "name": company["name"], "domain": company["domain"]},
            "filtered_by_keywords": kw_ids or [],
            "competitors": competitors,
        }

    @app.get("/api/competitors/{company_id}/gaps")
    async def get_gaps(company_id: int, competitor_domain: str):
        """Coverage gap analysis: where a competitor is listed but you are not."""
        if not competitor_domain:
            raise HTTPException(400, "competitor_domain query param required")
        return database.get_coverage_gaps(company_id, competitor_domain.strip().lower())

    @app.get("/api/listicles/{result_id}/companies")
    async def get_listicle_companies_endpoint(result_id: int):
        """Deep-dive: every company found on a specific listicle page."""
        companies = database.get_listicle_companies(result_id)
        return {"result_id": result_id, "companies": companies}

    # ── View cached search results ─────────────────────────────────────

    @app.get("/api/search/{search_id}")
    async def get_cached_results(search_id: int):
        results = database.get_cached_search_results(search_id)
        if not results:
            raise HTTPException(404, "Search not found")
        return {"results": results}

    # ── SERP comparison (verify cached vs current) ─────────────────────

    @app.post("/api/search/{search_id}/compare")
    async def compare_serp(search_id: int):
        """
        Re-fetch the SAME query (1 SERP call only — top 10 results) and compare
        against the cached results. Returns diff: new entries, lost entries,
        position shifts. Doesn't save the fresh results — just for verification.
        """
        import sqlite3

        # Get original search params
        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""SELECT s.id, s.domain, s.company_id, s.timestamp,
                            k.keyword, k.location
                     FROM searches s JOIN keywords k ON s.keyword_id = k.id
                     WHERE s.id = ?""", (search_id,))
        srow = c.fetchone()
        if not srow:
            conn.close()
            raise HTTPException(404, "Search not found")
        keyword = srow["keyword"]
        region = srow["location"] or "us"
        original_ts = srow["timestamp"]

        # Get cached results (URL → position)
        c.execute("""SELECT position, domain, url, page_type, status
                     FROM results WHERE search_id = ? ORDER BY position""", (search_id,))
        cached = [dict(r) for r in c.fetchall()]
        conn.close()

        if not cached:
            raise HTTPException(404, "No cached results for this search")

        # Fetch a fresh top-10 SERP — only 1 API call to keep cost low
        try:
            creds = agent.get_creds("free")
            fresh = agent.fetch_serp_page(keyword, creds, page_num=1, region=region)
        except Exception as e:
            raise HTTPException(500, f"Could not fetch fresh SERP: {e}")

        # Build comparison
        cached_by_url = {r["url"]: r["position"] for r in cached}
        fresh_by_url  = {item["url"]: item["position"] for item in fresh}

        new_entries  = [item for item in fresh if item["url"] not in cached_by_url]
        lost_entries = [r    for r    in cached if r["url"] not in fresh_by_url
                        and r["position"] <= 10]
        shifts = []
        for item in fresh:
            url = item["url"]
            if url in cached_by_url:
                old_pos = cached_by_url[url]
                new_pos = item["position"]
                if old_pos != new_pos:
                    shifts.append({
                        "url": url, "domain": item["domain"],
                        "title": item.get("title", ""),
                        "old_pos": old_pos, "new_pos": new_pos,
                        "delta": old_pos - new_pos,
                    })

        return {
            "search_id": search_id,
            "keyword": keyword,
            "region": region,
            "original_timestamp": original_ts,
            "cached_count": len(cached),
            "fresh_count": len(fresh),
            "cached_results": cached[:10],
            "fresh_results": fresh,
            "new_entries": new_entries,
            "lost_entries": lost_entries,
            "shifts": shifts,
        }

    # ── Re-run search ──────────────────────────────────────────────────

    @app.post("/api/search/{search_id}/rerun")
    async def rerun_search(search_id: int):
        """Re-run a past search using its stored parameters."""
        import sqlite3
        from pathlib import Path
        from queue import Queue
        import threading, uuid

        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""SELECT s.id, s.domain, s.company_id, k.keyword, k.location
                     FROM searches s JOIN keywords k ON s.keyword_id = k.id
                     WHERE s.id = ?""", (search_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            raise HTTPException(404, "Search not found")

        # Delegate to /api/search worker pattern
        run_id = uuid.uuid4().hex[:8]
        q: Queue = Queue()
        app.state.runs[run_id] = {"queue": q, "results": None, "error": None}

        def worker():
            try:
                company = database.get_company(row["company_id"]) if row["company_id"] else None
                name_variants = company["name_variants"] if company else None
                results = agent.run(
                    keyword=row["keyword"],
                    domain=row["domain"],
                    name_variants=name_variants,
                    mode="free",
                    target_listicles=10,
                    max_pages=10,
                    region=row["location"] or "us",
                    find_contacts=False,
                    progress_cb=lambda ev: q.put(ev),
                    write_file=False,
                )
                # Save fresh results as a new search entry
                serp_hash = database.get_serp_hash(results)
                keyword_rec = database.find_keyword(row["keyword"], row["location"] or "us")
                if not keyword_rec:
                    keyword_id = database.save_keyword(row["keyword"], row["location"] or "us", serp_hash)
                else:
                    keyword_id = keyword_rec[0]
                    conn = sqlite3.connect(database.DB_PATH)
                    conn.execute("UPDATE keywords SET serp_hash = ? WHERE id = ?", (serp_hash, keyword_id))
                    conn.commit()
                    conn.close()
                new_search_id = database.save_search(
                    keyword_id, row["domain"], len(results), company_id=row["company_id"]
                )
                database.save_results(new_search_id, results)
                # Persist extracted competitor companies
                for rr in results:
                    comps = rr.get("_extracted_companies")
                    if comps:
                        rid = database.find_result_id_by_url(rr["URL"], search_id=new_search_id)
                        if rid:
                            database.save_listicle_companies(rid, comps)
                app.state.runs[run_id]["results"] = results
                q.put({"type": "done", "results": results, "new_search_id": new_search_id})
            except Exception as e:
                app.state.runs[run_id]["error"] = str(e)
                q.put({"type": "error", "msg": str(e)})

        threading.Thread(target=worker, daemon=True).start()
        return {"run_id": run_id}

    # ── Bulk keyword search ────────────────────────────────────────────

    @app.post("/api/bulk-search")
    async def bulk_search(req: BulkSearchRequest):
        """Run multiple keywords sequentially under the same company."""
        import sqlite3
        from pathlib import Path
        from queue import Queue
        import threading, uuid

        keywords = [k.strip() for k in req.keywords if k.strip()]
        if not keywords:
            raise HTTPException(400, "No keywords provided")

        run_id = uuid.uuid4().hex[:8]
        q: Queue = Queue()
        app.state.runs[run_id] = {"queue": q, "results": None, "error": None}

        def worker():
            try:
                # Resolve company
                company = None
                name_variants = None
                search_domain = req.domain.strip() if req.domain else None
                if req.company_id:
                    company = database.get_company(req.company_id)
                    if company:
                        search_domain = company["domain"]
                        name_variants = company["name_variants"]
                elif search_domain:
                    company = database.get_company_by_domain(search_domain)
                    if company:
                        name_variants = company["name_variants"]

                all_results = []
                for idx, kw in enumerate(keywords, 1):
                    q.put({"type": "log", "msg": f"=== [{idx}/{len(keywords)}] {kw} ==="})
                    try:
                        results = agent.run(
                            keyword=kw, domain=search_domain,
                            name_variants=name_variants, mode=req.mode,
                            target_listicles=req.target_listicles,
                            max_pages=req.max_pages, region=req.region,
                            find_contacts=False,
                            progress_cb=lambda ev: q.put(ev),
                            write_file=False,
                        )
                        # Persist
                        serp_hash = database.get_serp_hash(results)
                        keyword_rec = database.find_keyword(kw, req.region)
                        if not keyword_rec:
                            keyword_id = database.save_keyword(kw, req.region, serp_hash)
                        else:
                            keyword_id = keyword_rec[0]
                            conn = sqlite3.connect(database.DB_PATH)
                            conn.execute("UPDATE keywords SET serp_hash = ? WHERE id = ?",
                                         (serp_hash, keyword_id))
                            conn.commit(); conn.close()
                        domain_to_save = database.normalize_domain(search_domain) if search_domain else None
                        company_id_save = company["id"] if company else req.company_id
                        s_id = database.save_search(keyword_id, domain_to_save,
                                                    len(results), company_id=company_id_save)
                        database.save_results(s_id, results)
                        # Persist extracted competitor companies
                        for rr in results:
                            comps = rr.get("_extracted_companies")
                            if comps:
                                rid = database.find_result_id_by_url(rr["URL"], search_id=s_id)
                                if rid:
                                    database.save_listicle_companies(rid, comps)
                        all_results.append({"keyword": kw, "count": len(results), "search_id": s_id})
                    except Exception as e:
                        q.put({"type": "log", "msg": f"   [FAIL] {kw}: {e}"})
                        all_results.append({"keyword": kw, "error": str(e)})

                app.state.runs[run_id]["results"] = all_results
                q.put({"type": "done", "results": all_results,
                       "summary": f"{len(all_results)} keywords processed"})
            except Exception as e:
                app.state.runs[run_id]["error"] = str(e)
                q.put({"type": "error", "msg": str(e)})

        threading.Thread(target=worker, daemon=True).start()
        return {"run_id": run_id, "keyword_count": len(keywords)}
