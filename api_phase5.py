"""
Phase 5 endpoints — Dashboard, Settings, Power Features.
Imported and registered onto the main app in api.py.
"""

from fastapi import HTTPException
from pydantic import BaseModel
import requests as _http
import re


# ── Pydantic models ──────────────────────────────────────────────────────

class AggregatorRequest(BaseModel):
    domain: str


class VideoDomainRequest(BaseModel):
    domain: str


class CrossVerifyRequest(BaseModel):
    providers:   list[str] = ["serper", "semrush"]
    force_fresh: bool      = False  # If True, ignore cache and fetch fresh


class MultiRegionSearchRequest(BaseModel):
    keyword:          str
    regions:          list[str]  = ["us", "uk", "in"]
    company_id:       int | None = None
    target_listicles: int        = 10
    max_pages:        int        = 5
    mode:             str        = "free"


class MultiRegionMergeRequest(BaseModel):
    search_ids: list[int]
    export:     bool = False  # If true, returns Excel file instead of JSON


class CompetitorMineRequest(BaseModel):
    region:        str = "us"
    display_limit: int = 10
    force_fresh:   bool = False


class ListicleScoreRequest(BaseModel):
    force_fresh: bool = False


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

    # ── Cross-verify SERP (Serper + Semrush) ───────────────────────────

    @app.get("/api/cross-verify/{search_id}/preview")
    async def cross_verify_preview(search_id: int):
        """
        Preview which providers are cached vs need fresh API calls.
        Returns cache status per provider + estimated cost.
        """
        import sqlite3
        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""SELECT s.id, k.keyword, k.location, s.timestamp
                     FROM searches s JOIN keywords k ON s.keyword_id = k.id
                     WHERE s.id = ?""", (search_id,))
        srow = c.fetchone()
        conn.close()
        if not srow:
            raise HTTPException(404, "Search not found")

        cache_status = database.get_cross_verify_status(search_id, max_age_hours=12)

        # Compute per-provider availability + cost
        providers_info = {}
        # Serper
        serper_key = database.get_active_api_key("serper")
        cached = cache_status.get("serper", {})
        providers_info["serper"] = {
            "name": "Serper.dev",
            "available": bool(serper_key),
            "cached": cached.get("fresh", False),
            "age_hours": cached.get("age_hours"),
            "fetched_at": cached.get("fetched_at"),
            "cost_per_call": "1 credit",
            "cost_unit": "credit",
            "free_if_cached": True,
        }
        # Semrush
        semrush_key = database.get_active_api_key("semrush")
        cached = cache_status.get("semrush", {})
        providers_info["semrush"] = {
            "name": "Semrush phrase_organic",
            "available": bool(semrush_key),
            "cached": cached.get("fresh", False),
            "age_hours": cached.get("age_hours"),
            "fetched_at": cached.get("fetched_at"),
            "cost_per_call": "10 units",
            "cost_unit": "units",
            "free_if_cached": True,
        }

        return {
            "search_id": search_id,
            "keyword": srow["keyword"],
            "region": srow["location"] or "us",
            "search_timestamp": srow["timestamp"],
            "cache_window_hours": 12,
            "providers": providers_info,
        }

    @app.post("/api/cross-verify/{search_id}")
    async def cross_verify_run(search_id: int, req: CrossVerifyRequest):
        """
        Run cross-verification. For each provider:
          - If cached (<12h) and not force_fresh → use cache
          - Else → fetch fresh + save to cache
        Then merge results into a comparison table with confidence flags.
        """
        import sqlite3
        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""SELECT s.id, k.keyword, k.location
                     FROM searches s JOIN keywords k ON s.keyword_id = k.id
                     WHERE s.id = ?""", (search_id,))
        srow = c.fetchone()
        conn.close()
        if not srow:
            raise HTTPException(404, "Search not found")
        keyword = srow["keyword"]
        region  = srow["location"] or "us"

        providers = [p.strip().lower() for p in (req.providers or []) if p.strip()]
        if not providers:
            raise HTTPException(400, "No providers selected")

        # Per-provider data: list of {position, domain, url, title}
        per_provider = {}
        used_cache_for = []
        fetched_fresh_for = []
        cost_summary = {"serper": 0, "semrush": 0}  # credits/units consumed

        for prov in providers:
            cached_results, fetched_at = (None, None)
            if not req.force_fresh:
                cached_results, fetched_at = database.get_cross_verify_cache(
                    search_id, prov, max_age_hours=12)

            if cached_results is not None:
                per_provider[prov] = {
                    "results": cached_results,
                    "source":  "cache",
                    "fetched_at": fetched_at,
                }
                used_cache_for.append(prov)
                continue

            # Need to fetch fresh
            try:
                if prov == "serper":
                    creds = agent.get_creds("free")
                    if creds.get("provider") != "serper":
                        per_provider[prov] = {"results": [], "source": "no_key",
                                              "error": "Serper.dev key not configured"}
                        continue
                    results = agent.fetch_serp_page(keyword, creds, page_num=1, region=region)
                    cost_summary["serper"] += 1
                elif prov == "semrush":
                    skey_row = database.get_active_api_key("semrush")
                    if not skey_row:
                        per_provider[prov] = {"results": [], "source": "no_key",
                                              "error": "Semrush key not configured"}
                        continue
                    results = agent.fetch_semrush_phrase_organic(
                        keyword, region, skey_row["api_key"],
                        key_id=skey_row.get("id"), display_limit=100)
                    cost_summary["semrush"] += 10
                else:
                    per_provider[prov] = {"results": [], "source": "unknown_provider"}
                    continue

                # Save to cache
                database.save_cross_verify_cache(search_id, prov, results)
                per_provider[prov] = {
                    "results": results,
                    "source":  "fresh",
                }
                fetched_fresh_for.append(prov)
            except Exception as e:
                per_provider[prov] = {"results": [], "source": "error", "error": str(e)}

        # Build merged comparison
        # url → {url, domain, positions: {prov: int}, providers_count}
        merged = {}
        for prov, data in per_provider.items():
            for item in (data.get("results") or []):
                url = item.get("url", "").strip()
                if not url:
                    continue
                dom = item.get("domain", "").lower().replace("www.", "")
                if url not in merged:
                    merged[url] = {
                        "url": url, "domain": dom, "title": item.get("title", ""),
                        "positions": {},
                    }
                merged[url]["positions"][prov] = item.get("position")

        # Convert to list + compute confidence + best position + spread
        merged_list = []
        active_providers = [p for p in providers if per_provider.get(p, {}).get("source") != "no_key"
                                                  and per_provider.get(p, {}).get("source") != "unknown_provider"]
        total_provs = max(1, len(active_providers))

        for url, row in merged.items():
            positions = [p for p in row["positions"].values() if p is not None]
            n_providers = len(positions)
            best = min(positions) if positions else None
            spread = (max(positions) - min(positions)) if len(positions) > 1 else 0

            if n_providers == total_provs and total_provs >= 2:
                confidence = "high"
            elif n_providers >= 2:
                confidence = "medium"
            else:
                confidence = "low"

            row["providers_count"] = n_providers
            row["best_position"]   = best
            row["spread"]          = spread
            row["confidence"]      = confidence
            merged_list.append(row)

        # Sort by best position
        merged_list.sort(key=lambda r: r["best_position"] if r["best_position"] is not None else 9999)

        # Stats
        stats = {
            "total_unique_urls": len(merged_list),
            "high_confidence":   sum(1 for r in merged_list if r["confidence"] == "high"),
            "medium_confidence": sum(1 for r in merged_list if r["confidence"] == "medium"),
            "low_confidence":    sum(1 for r in merged_list if r["confidence"] == "low"),
        }

        return {
            "search_id": search_id,
            "keyword": keyword,
            "region": region,
            "providers_queried": providers,
            "active_providers": active_providers,
            "per_provider_summary": {
                p: {
                    "count":      len(per_provider.get(p, {}).get("results") or []),
                    "source":     per_provider.get(p, {}).get("source"),
                    "fetched_at": per_provider.get(p, {}).get("fetched_at"),
                    "error":      per_provider.get(p, {}).get("error"),
                } for p in providers
            },
            "merged_results": merged_list,
            "stats": stats,
            "cost_consumed": cost_summary,
            "used_cache_for": used_cache_for,
            "fetched_fresh_for": fetched_fresh_for,
        }

    # ── Multi-region bundle search (Serper only — cheap) ───────────────

    @app.post("/api/search/multi-region")
    async def multi_region_search(req: MultiRegionSearchRequest):
        """
        Run the same Serper search across multiple regions sequentially.
        Cost: 1 Serper credit per region (plus N for additional SERP pages).
        Each region becomes its own search entry in history.
        """
        from queue import Queue
        import threading, uuid

        if not req.keyword.strip():
            raise HTTPException(400, "keyword required")
        if not req.regions:
            raise HTTPException(400, "select at least one region")

        run_id = uuid.uuid4().hex[:8]
        q: Queue = Queue()
        app.state.runs[run_id] = {"queue": q, "results": None, "error": None}

        def worker():
            try:
                company = None
                name_variants = None
                if req.company_id:
                    company = database.get_company(req.company_id)
                    if company:
                        name_variants = company["name_variants"]

                summary_per_region = []
                for region in req.regions:
                    q.put({"type": "log", "msg": f"=== Region: {region.upper()} ==="})
                    try:
                        results = agent.run(
                            keyword=req.keyword,
                            domain=(company["domain"] if company else None),
                            name_variants=name_variants,
                            mode=req.mode,
                            target_listicles=req.target_listicles,
                            max_pages=req.max_pages,
                            region=region,
                            find_contacts=False,
                            progress_cb=lambda ev: q.put(ev),
                            write_file=False,
                        )
                        # Persist
                        import sqlite3
                        serp_hash = database.get_serp_hash(results)
                        kr = database.find_keyword(req.keyword, region)
                        if not kr:
                            kid = database.save_keyword(req.keyword, region, serp_hash)
                        else:
                            kid = kr[0]
                            conn = sqlite3.connect(database.DB_PATH)
                            conn.execute("UPDATE keywords SET serp_hash = ? WHERE id = ?",
                                         (serp_hash, kid))
                            conn.commit(); conn.close()
                        dom_save = (company["domain"] if company else None)
                        sid = database.save_search(kid, dom_save, len(results),
                                                   company_id=(company["id"] if company else None))
                        database.save_results(sid, results)
                        # Persist extracted competitors
                        for rr in results:
                            comps = rr.get("_extracted_companies")
                            if comps:
                                rid = database.find_result_id_by_url(rr["URL"], search_id=sid)
                                if rid:
                                    database.save_listicle_companies(rid, comps)
                        summary_per_region.append({
                            "region": region, "search_id": sid, "count": len(results),
                        })
                    except Exception as e:
                        q.put({"type": "log", "msg": f"[FAIL] {region}: {e}"})
                        summary_per_region.append({"region": region, "error": str(e)})

                app.state.runs[run_id]["results"] = summary_per_region
                q.put({"type": "done", "results": summary_per_region})
            except Exception as e:
                app.state.runs[run_id]["error"] = str(e)
                q.put({"type": "error", "msg": str(e)})

        threading.Thread(target=worker, daemon=True).start()
        return {"run_id": run_id, "regions": req.regions, "estimated_serper_credits": len(req.regions)}

    @app.post("/api/search/multi-region/merge")
    async def merge_multi_region(req: MultiRegionMergeRequest):
        """
        Merge several searches (typically a multi-region bundle) into a single
        wide-format view: one row per URL with columns per region.
        Returns merged JSON; if export=true, returns Excel file.
        """
        import sqlite3, io
        if not req.search_ids:
            raise HTTPException(400, "search_ids required")

        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        placeholders = ",".join("?" * len(req.search_ids))
        c.execute(f"""
            SELECT s.id as search_id, k.keyword, k.location,
                   r.url, r.domain, r.title, r.page_type,
                   r.position, r.status, r.position_on_page, r.link_type
            FROM searches s
            JOIN keywords k ON s.keyword_id = k.id
            JOIN results r ON r.search_id = s.id
            WHERE s.id IN ({placeholders})
            ORDER BY r.position
        """, req.search_ids)
        rows = [dict(r) for r in c.fetchall()]

        # Get unique keyword (should all be the same in a bundle)
        c.execute(f"SELECT DISTINCT keyword FROM keywords WHERE id IN "
                  f"(SELECT keyword_id FROM searches WHERE id IN ({placeholders}))",
                  req.search_ids)
        kws = [r[0] for r in c.fetchall()]
        keyword = kws[0] if kws else "(merged)"
        conn.close()

        # Build wide format: dict[url] = {url, domain, page_type, per_region: {pos, status, link_type}}
        regions_in_set = sorted(set(r["location"] for r in rows if r["location"]))
        merged = {}
        for r in rows:
            url = (r["url"] or "").strip()
            if not url:
                continue
            if url not in merged:
                merged[url] = {
                    "url": url,
                    "domain": r["domain"],
                    "title": r.get("title", ""),
                    "page_type": r["page_type"],
                    "by_region": {},
                }
            region = r["location"] or "?"
            merged[url]["by_region"][region] = {
                "serp_pos":   r["position"],
                "status":     r["status"] or "",
                "page_pos":   r["position_on_page"] or "",
                "link_type":  r["link_type"] or "",
            }

        merged_list = list(merged.values())
        # Compute best_pos + region_count for sorting
        for row in merged_list:
            positions = [d.get("serp_pos") for d in row["by_region"].values()
                         if d.get("serp_pos") is not None]
            row["best_pos"] = min(positions) if positions else None
            row["region_count"] = len(row["by_region"])
            row["regions_listed"] = sorted(row["by_region"].keys())
        merged_list.sort(key=lambda r: (r["best_pos"] if r["best_pos"] else 9999,
                                        -r["region_count"]))

        stats = {
            "total_urls":   len(merged_list),
            "multi_region": sum(1 for r in merged_list if r["region_count"] > 1),
            "single_region": sum(1 for r in merged_list if r["region_count"] == 1),
            "regions":      regions_in_set,
        }

        if not req.export:
            return {
                "keyword": keyword,
                "regions": regions_in_set,
                "merged_results": merged_list,
                "stats": stats,
            }

        # Generate wide-format Excel
        buf = io.BytesIO()
        agent.write_excel_multi_region(keyword, merged_list, regions_in_set, buf)
        buf.seek(0)
        from datetime import datetime
        now = datetime.now()
        safe = re.sub(r"[^A-Za-z0-9]+", "_", keyword).strip("_")[:50]
        fname = f"{safe}_MultiRegion_{now.strftime('%Y-%m-%d_%A')}.xlsx"
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    # ── Competitor keyword mining (Semrush domain_organic) ─────────────

    @app.get("/api/competitors/mine-preview/{company_id}")
    async def mine_preview(company_id: int, competitor_domain: str, region: str = "us"):
        """Show cache status + cost estimate BEFORE spending Semrush units."""
        dom = (competitor_domain or "").strip().lower().replace("www.", "")
        if not dom:
            raise HTTPException(400, "competitor_domain required")
        status = database.semrush_cache_status("domain_organic", dom, region)
        spent_month = database.get_semrush_units_spent("month")
        return {
            "company_id": company_id,
            "competitor_domain": dom,
            "region": region,
            "cache": status,
            "cost_if_fresh": 10,
            "cost_unit": "Semrush units",
            "will_be_free_if_cached": status.get("fresh", False),
            "semrush_spent_this_month": spent_month["units_spent"],
        }

    @app.post("/api/competitors/mine/{company_id}")
    async def mine_competitor(company_id: int, competitor_domain: str,
                              req: CompetitorMineRequest):
        """
        Fetch keywords competitor ranks for (Semrush domain_organic, 10 units).
        Cached 30 days. Returns top 10 keywords by traffic.
        """
        dom = (competitor_domain or "").strip().lower().replace("www.", "")
        if not dom:
            raise HTTPException(400, "competitor_domain required")
        company = database.get_company(company_id)
        if not company:
            raise HTTPException(404, "company not found")
        skey_row = database.get_active_api_key("semrush")
        if not skey_row:
            raise HTTPException(400, "Semrush API key not configured")

        # Check cache unless force_fresh
        if not req.force_fresh:
            cached, fetched_at = database.get_semrush_cache("domain_organic", dom, req.region)
            if cached is not None:
                return {
                    "competitor_domain": dom, "region": req.region,
                    "source": "cache", "fetched_at": fetched_at,
                    "units_spent": 0, "keywords": cached,
                }

        # Fresh fetch
        results = agent.fetch_semrush_domain_organic(
            dom, req.region, skey_row["api_key"],
            key_id=skey_row.get("id"), display_limit=req.display_limit,
        )
        return {
            "competitor_domain": dom, "region": req.region,
            "source": "fresh", "units_spent": 10,
            "keywords": results,
        }

    # ── Listicle priority score (opt-in per listicle) ─────────────────

    @app.get("/api/listicles/{result_id}/score-preview")
    async def score_preview(result_id: int):
        """Show cache + cost estimate for scoring a listicle."""
        info = database.get_result_basic(result_id)
        if not info:
            raise HTTPException(404, "result not found")
        url = info["url"]
        region = info["location"] or "us"
        existing = database.get_listicle_score(result_id)
        url_cache = database.semrush_cache_status("url_organic", url, region)
        return {
            "result_id": result_id,
            "url": url, "domain": info["domain"], "region": region,
            "already_scored": existing is not None,
            "current_score": existing["priority_score"] if existing else None,
            "scored_at": existing["scored_at"] if existing else None,
            "url_organic_cache": url_cache,
            "cost_if_fresh": 10,
            "will_be_free_if_cached": url_cache.get("fresh", False) or existing is not None,
        }

    @app.post("/api/listicles/{result_id}/score")
    async def score_listicle(result_id: int, req: ListicleScoreRequest):
        """
        Compute priority score for a listicle.
        Cost: 10 Semrush units (url_organic) — IF not cached.
        Formula: authority × log(kw+1) × competitor_density × you_not_listed_bonus
        Cached 14 days.
        """
        info = database.get_result_basic(result_id)
        if not info:
            raise HTTPException(404, "result not found")
        url = info["url"]
        region = info["location"] or "us"
        domain = info["domain"]

        # If already scored & not force_fresh → return cached
        if not req.force_fresh:
            existing = database.get_listicle_score(result_id)
            if existing:
                return {
                    "source": "cache", "result_id": result_id,
                    "score": existing["priority_score"],
                    "breakdown": existing.get("breakdown", {}),
                    "units_spent": 0,
                }

        # Fetch Semrush url_organic
        skey_row = database.get_active_api_key("semrush")
        sem_data = {"keyword_count": 0, "top_keywords": [], "top_traffic_pct": 0}
        units_spent = 0
        if skey_row:
            sem_data = agent.fetch_semrush_url_organic(
                url, region, skey_row["api_key"], key_id=skey_row.get("id"))
            # Check if Semrush actually fetched fresh (vs cache) — cache age tells us
            url_cache_st = database.semrush_cache_status("url_organic", url, region)
            if url_cache_st.get("age_hours", 999) < 0.1:  # fresh fetch in last few seconds
                units_spent = 10

        # Get authority from OPR
        opr_key_row = database.get_active_api_key("openpagerank")
        opr_key = opr_key_row["api_key"] if opr_key_row else ""
        authority = 0
        if opr_key and domain:
            try:
                opr_data = agent.fetch_openpagerank([domain], opr_key,
                                                     opr_key_id=opr_key_row.get("id") if opr_key_row else None)
                a = opr_data.get(domain, 0)
                authority = float(a) if a not in ("", None) else 0
            except Exception:
                authority = 0

        # Competitor density — count distinct competitor domains on this listicle
        listicle_comps = database.get_listicle_companies(result_id)
        competitor_count = len([c for c in listicle_comps if c.get("domain")])
        # Is your company listed here? (status == 'Listed')
        you_listed = info.get("status") == "Listed"

        # Score formula
        # Authority base (0-100), capped contribution 0-1
        a_norm = min(authority / 100.0, 1.0) if authority else 0
        # Keyword count log-scale
        import math
        kw_factor = math.log10(sem_data["keyword_count"] + 1) / 3  # 0-1 for 0-1000 kw
        kw_factor = min(kw_factor, 1.0)
        # Competitor density — more competitors = stronger listicle
        comp_factor = min(competitor_count / 10.0, 1.0)  # cap at 10
        # Opportunity bonus — being NOT listed = 1.5x
        opp_bonus = 1.0 if you_listed else 1.5

        raw = (a_norm * 0.35 + kw_factor * 0.35 + comp_factor * 0.30) * opp_bonus
        priority = round(min(raw * 100, 100), 1)

        breakdown = {
            "authority_norm": round(a_norm, 3),
            "keyword_count": sem_data["keyword_count"],
            "kw_factor": round(kw_factor, 3),
            "competitor_count": competitor_count,
            "comp_factor": round(comp_factor, 3),
            "you_listed": you_listed,
            "opportunity_bonus": opp_bonus,
            "top_keywords": sem_data["top_keywords"][:5],
        }

        database.save_listicle_score(result_id, authority, sem_data["keyword_count"],
                                     competitor_count, you_listed, priority, breakdown)
        return {
            "source": "fresh", "result_id": result_id,
            "score": priority, "breakdown": breakdown,
            "units_spent": units_spent,
        }

    # ── Semrush spend dashboard ────────────────────────────────────────

    @app.post("/api/maintenance/dedupe-results")
    async def dedupe_results():
        """One-time cleanup: removes duplicate URLs within each search."""
        result = database.dedupe_existing_results()
        return result

    @app.get("/api/semrush/spend")
    async def semrush_spend():
        """Real-time Semrush spending — today + this month."""
        today = database.get_semrush_units_spent("day")
        month = database.get_semrush_units_spent("month")
        # Active key for quota
        skey = database.get_active_api_key("semrush")
        monthly_limit = skey.get("monthly_limit") if skey else None
        return {
            "today_units":   today["units_spent"],
            "today_calls":   today["calls"],
            "month_units":   month["units_spent"],
            "month_calls":   month["calls"],
            "monthly_limit": monthly_limit,
            "pct_used":      round(month["units_spent"] / monthly_limit * 100, 1) if monthly_limit else None,
        }

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
