"""
PropAI Scraper – FastAPI Service
Scrapes ImmoScout24 and calculates investment metrics.
Run: uvicorn app.main:app --reload --port 8001
"""

from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import asyncio
import logging

from .scraper import ImmoScout24Scraper
from .models import SearchParams, SearchResult, ScrapeStatus
from .calculator import InvestmentCalculator
from .storage import SupabaseStorage
from .keepalive import keep_alive

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PropAI Scraper API",
    description="Real estate data scraper for ImmoScout24 with investment calculations",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Start keep-alive background task on server boot."""
    import asyncio
    asyncio.create_task(keep_alive())
    logger.info("✓ Server started – keep-alive active")

scraper = ImmoScout24Scraper()
calculator = InvestmentCalculator()
storage = SupabaseStorage()

# ── Status tracking ───────────────────────────────────────────────────────────
scrape_jobs: dict[str, ScrapeStatus] = {}


@app.get("/")
async def root():
    return {"status": "ok", "service": "PropAI Scraper", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "scraper": "ready"}


# ── Main search endpoint ──────────────────────────────────────────────────────
@app.post("/search", response_model=SearchResult)
async def search(params: SearchParams):
    """
    Search ImmoScout24 and return enriched listings with investment metrics.
    This is the main endpoint called by the PropAI frontend.
    """
    logger.info(f"Search: {params.ort}, type={params.objekttyp}, max={params.max_price}")
    
    try:
        # 1. Scrape raw listings
        listings = await scraper.search(params)
        
        # 2. Enrich with investment calculations
        enriched = [calculator.enrich(listing, params) for listing in listings]
        
        # 3. Sort by ROI descending
        enriched.sort(key=lambda x: x.get("roi", 0), reverse=True)
        
        # 4. Optionally save to Supabase
        if params.save_to_db and enriched:
            await storage.save_listings(enriched, params)
        
        return SearchResult(
            listings=enriched,
            total=len(enriched),
            ort=params.ort,
            source="immoscout24"
        )
    
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Single listing detail ─────────────────────────────────────────────────────
@app.get("/listing/{listing_id}")
async def get_listing(listing_id: str):
    """Fetch full details for a single listing."""
    try:
        detail = await scraper.get_detail(listing_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Listing not found")
        enriched = calculator.enrich(detail, None)
        return enriched
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Background job: full city scan ───────────────────────────────────────────
@app.post("/scan/{ort}")
async def start_scan(
    ort: str,
    background_tasks: BackgroundTasks,
    max_pages: int = Query(default=5, le=20)
):
    """
    Start a background scan of all listings in a city.
    Returns a job_id to check status.
    """
    import uuid
    job_id = str(uuid.uuid4())[:8]
    scrape_jobs[job_id] = ScrapeStatus(job_id=job_id, ort=ort, status="running")
    
    background_tasks.add_task(_run_scan, job_id, ort, max_pages)
    return {"job_id": job_id, "status": "started", "ort": ort}


@app.get("/scan/status/{job_id}")
async def get_scan_status(job_id: str):
    if job_id not in scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return scrape_jobs[job_id]


async def _run_scan(job_id: str, ort: str, max_pages: int):
    """Background task: scan all pages for a city."""
    try:
        params = SearchParams(ort=ort, max_pages=max_pages, save_to_db=True)
        listings = await scraper.search(params)
        enriched = [calculator.enrich(l, params) for l in listings]
        await storage.save_listings(enriched, params)
        
        scrape_jobs[job_id].status = "done"
        scrape_jobs[job_id].count = len(enriched)
        logger.info(f"Scan {job_id} done: {len(enriched)} listings")
    except Exception as e:
        scrape_jobs[job_id].status = "error"
        scrape_jobs[job_id].error = str(e)
        logger.error(f"Scan {job_id} failed: {e}")
