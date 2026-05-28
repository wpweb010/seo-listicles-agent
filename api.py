"""
SEO Listicles Agent — FastAPI backend
======================================
Run with:
    uvicorn api:app --reload --port 8000
Then open:
    http://localhost:8000
"""

import asyncio
import io
import json
import re
import threading
import uuid
from pathlib import Path
from queue import Empty, Queue

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import seo_listicles_agent as agent
from database import (
    init_db, get_serp_hash, find_keyword, save_keyword, save_search,
    save_results, get_history, get_results_for_export, get_domains_in_history,
    normalize_domain, clear_all_history, delete_search,
    create_company, update_company, delete_company, get_companies,
    get_company, get_company_by_domain, get_history_by_company,
    get_results_by_company,
)

# Initialize database on startup
init_db()

app = FastAPI(title="SEO Listicles Agent", version="1.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory run store — fine for a local single-user tool
_runs: dict[str, dict] = {}


# ── Request / response models ─────────────────────────────────────────────────

class SearchRequest(BaseModel):
    keyword:          str
    domain:           str         = ""
    company_id:       int | None  = None
    region:           str         = "us"
    target_listicles: int         = Field(10, ge=5, le=50)
    max_pages:        int         = Field(20, ge=1, le=50)
    mode:             str         = "free"
    contacts:         bool        = False


class ExportRequest(BaseModel):
    keyword: str
    results: list


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(500, "index.html not found in static/")
    return HTMLResponse(
        content=html_path.read_text(encoding="utf-8"),
        media_type="text/html; charset=utf-8",
    )


@app.get("/api/regions")
async def list_regions():
    return [
        {"code": code, "label": info["label"]}
        for code, info in agent.REGION_MAP.items()
    ]


@app.post("/api/search")
async def start_search(req: SearchRequest):
    """Start a search run in a background thread; return a run_id."""
    run_id = uuid.uuid4().hex[:8]
    q: Queue = Queue()
    _runs[run_id] = {"queue": q, "results": None, "error": None}

    def worker():
        try:
            # Resolve company + variants
            company = None
            name_variants = None
            search_domain = req.domain.strip() if req.domain else None

            if req.company_id:
                company = get_company(req.company_id)
                if company:
                    search_domain = company["domain"]
                    name_variants = company["name_variants"]
                    q.put({"type": "log", "msg": f"Using company profile: {company['name']} ({len(name_variants)} variants)"})
            elif search_domain:
                # Auto-find company by domain
                company = get_company_by_domain(search_domain)
                if company:
                    name_variants = company["name_variants"]

            # Run the search
            results = agent.run(
                keyword           = req.keyword,
                domain            = search_domain,
                name_variants     = name_variants,
                mode              = req.mode,
                target_listicles  = req.target_listicles,
                max_pages         = req.max_pages,
                region            = req.region,
                find_contacts     = req.contacts,
                progress_cb       = lambda ev: q.put(ev),
                write_file        = False,
            )

            # Save to history
            import sqlite3
            serp_hash = get_serp_hash(results)
            keyword_rec = find_keyword(req.keyword, req.region)

            if not keyword_rec:
                keyword_id = save_keyword(req.keyword, req.region, serp_hash)
            else:
                keyword_id = keyword_rec[0]
                conn = sqlite3.connect(Path(__file__).parent / "search_history.db")
                conn.execute("UPDATE keywords SET serp_hash = ? WHERE id = ?", (serp_hash, keyword_id))
                conn.commit()
                conn.close()

            domain_to_save = normalize_domain(search_domain) if search_domain else None
            company_id_to_save = company["id"] if company else req.company_id
            search_id = save_search(keyword_id, domain_to_save, len(results), company_id=company_id_to_save)
            save_results(search_id, results)

            _runs[run_id]["results"] = results
            q.put({"type": "done", "results": results})
        except Exception as exc:
            _runs[run_id]["error"] = str(exc)
            q.put({"type": "error", "msg": str(exc)})

    threading.Thread(target=worker, daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/stream/{run_id}")
async def stream_events(run_id: str):
    """
    Server-Sent Events stream for live progress.
    Emits {"type": "log", "msg": "..."} events during the run,
    {"type": "done", "results": [...]} when complete,
    {"type": "error", "msg": "..."} on failure.
    """
    if run_id not in _runs:
        raise HTTPException(404, "Run not found")

    async def generator():
        q     = _runs[run_id]["queue"]
        loop  = asyncio.get_event_loop()
        while True:
            try:
                ev = await loop.run_in_executor(None, lambda: q.get(timeout=120))
            except Empty:
                yield "data: {\"type\": \"error\", \"msg\": \"Timed out\"}\n\n"
                break
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("type") in ("done", "error"):
                break

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/export")
async def export_excel(req: ExportRequest):
    """Accept results JSON; return an Excel file download."""
    buf = io.BytesIO()
    # Extract region from results if available
    region = "us"
    if req.results:
        # Try to extract region from first result if available
        region = "us"  # default
    agent.write_excel(req.keyword, req.results, buf, region=region)
    buf.seek(0)
    safe     = re.sub(r"[^a-z0-9]+", "_", req.keyword.lower()).strip("_")
    filename = f"listicles_{safe}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/history")
async def get_search_history(domain: str = None):
    """Get search history, optionally filtered by domain."""
    try:
        history = get_history(domain=domain)
        return {"history": history}
    except Exception as e:
        raise HTTPException(500, f"Error fetching history: {str(e)}")


@app.get("/api/domains")
async def get_all_domains():
    """Get list of unique domains in search history."""
    try:
        domains = get_domains_in_history()
        return {"domains": domains}
    except Exception as e:
        raise HTTPException(500, f"Error fetching domains: {str(e)}")


# ── Company management endpoints ──────────────────────────────────────────────

class CompanyCreateRequest(BaseModel):
    name:            str
    domain:          str
    custom_variants: list = []


class CompanyUpdateRequest(BaseModel):
    name:            str | None = None
    custom_variants: list | None = None


@app.get("/api/companies")
async def list_companies():
    """List all companies with search counts."""
    return {"companies": get_companies()}


@app.post("/api/companies")
async def add_company(req: CompanyCreateRequest):
    """Create a company profile."""
    if not req.name or not req.domain:
        raise HTTPException(400, "name and domain are required")
    company_id = create_company(req.name, req.domain, req.custom_variants)
    return {"id": company_id, "company": get_company(company_id)}


@app.put("/api/companies/{company_id}")
async def edit_company(company_id: int, req: CompanyUpdateRequest):
    """Update a company's name and/or variants."""
    update_company(company_id, name=req.name, custom_variants=req.custom_variants)
    return {"company": get_company(company_id)}


@app.delete("/api/companies/{company_id}")
async def remove_company(company_id: int):
    """Delete a company profile (searches remain, just unlinked)."""
    delete_company(company_id)
    return {"status": "deleted"}


@app.get("/api/companies/{company_id}/history")
async def company_history(company_id: int):
    """Get all searches for a company."""
    return {"history": get_history_by_company(company_id)}


class CompanyExportRequest(BaseModel):
    search_ids: list | None = None  # Optional: select specific searches; default = all


@app.post("/api/companies/{company_id}/export")
async def export_company(company_id: int, req: CompanyExportRequest):
    """Export a company's searches to Excel."""
    company = get_company(company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    results = get_results_by_company(company_id, search_ids=req.search_ids)
    if not results:
        raise HTTPException(404, "No results found for this company")

    buf = io.BytesIO()
    agent.write_excel_company(company["name"], company["domain"], results, buf)
    buf.seek(0)

    # Filename: WPWeb_Infotech_Outreach_2026-05-25_Monday.xlsx
    from datetime import datetime
    now = datetime.now()
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", company["name"]).strip("_")
    date_str = now.strftime("%Y-%m-%d")
    day_str  = now.strftime("%A")
    filename = f"{safe_name}_Outreach_{date_str}_{day_str}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class VerifyUrlRequest(BaseModel):
    url:    str
    domain: str = ""


@app.post("/api/verify-url")
async def verify_url(req: VerifyUrlRequest):
    """
    Diagnostic endpoint: fetch a URL and verify whether a domain is listed.
    Returns detailed audit trail for user-facing transparency.
    """
    try:
        result = agent.verify_url_diagnostic(req.url, req.domain)
        return result
    except Exception as e:
        raise HTTPException(500, f"Error verifying URL: {str(e)}")


@app.delete("/api/history")
async def clear_history():
    """Clear all search history."""
    try:
        clear_all_history()
        return {"status": "cleared"}
    except Exception as e:
        raise HTTPException(500, f"Error clearing history: {str(e)}")


@app.delete("/api/history/{search_id}")
async def delete_one_search(search_id: int):
    """Delete a specific search from history."""
    try:
        delete_search(search_id)
        return {"status": "deleted", "search_id": search_id}
    except Exception as e:
        raise HTTPException(500, f"Error deleting search: {str(e)}")


class HistoryExportRequest(BaseModel):
    search_ids: list | None = None
    domain_filter: str | None = None


@app.post("/api/export-history")
async def export_history_data(req: HistoryExportRequest):
    """Export history data for selected searches and domain filter."""
    try:
        results = get_results_for_export(
            search_ids=req.search_ids,
            domain_filter=req.domain_filter
        )

        if not results:
            raise HTTPException(404, "No results found for the selected criteria")

        # Determine company context (if any) for the searched domain
        company = None
        if req.domain_filter and req.domain_filter != "__none__":
            company = get_company_by_domain(req.domain_filter)

        buf = io.BytesIO()
        # If domain filter resolves to a company, include company context in the sheet
        if company:
            agent.write_excel_history(results, buf, header_context={
                "company_name":   company["name"],
                "company_domain": company["domain"],
            })
        else:
            agent.write_excel_history(results, buf)
        buf.seek(0)

        # Smart filename — use company name if available, else generic
        from datetime import datetime
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        day_str  = now.strftime("%A")
        if company:
            safe_name = re.sub(r"[^A-Za-z0-9]+", "_", company["name"]).strip("_")
            filename = f"{safe_name}_Outreach_{date_str}_{day_str}.xlsx"
        elif req.domain_filter == "__none__":
            filename = f"keyword_research_{date_str}_{day_str}.xlsx"
        else:
            filename = f"listicles_history_{date_str}_{day_str}.xlsx"

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error exporting history: {str(e)}")
