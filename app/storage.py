"""
PropAI Scraper – Supabase Storage

Saves scraped listings to Supabase so the PropAI frontend
can query them directly.
"""

import os
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SupabaseStorage:

    def __init__(self):
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize Supabase client from env vars."""
        try:
            from supabase import create_client
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_KEY")  # use service key for writes
            if url and key:
                self._client = create_client(url, key)
                logger.info("✓ Supabase connected")
            else:
                logger.warning("No SUPABASE_URL/KEY – storage disabled")
        except ImportError:
            logger.warning("supabase package not installed – storage disabled")
        except Exception as e:
            logger.error(f"Supabase init error: {e}")

    async def save_listings(self, listings: list, params) -> int:
        """
        Upsert listings to Supabase 'listings' table.
        Returns number of saved records.
        """
        if not self._client or not listings:
            return 0

        rows = []
        for l in listings:
            rows.append({
                "id":               l.get("id"),
                "titel":            l.get("titel", ""),
                "adresse":          l.get("adresse", ""),
                "ort":              l.get("ort", ""),
                "plz":              l.get("plz", ""),
                "preis":            l.get("preis"),
                "preis_m2":         l.get("preis_m2"),
                "wohnflaeche":      l.get("wohnflaeche"),
                "zimmer":           l.get("zimmer"),
                "baujahr":          l.get("baujahr"),
                "objekttyp":        l.get("objekttyp", ""),
                "zustand":          l.get("zustand", ""),
                "energie_klasse":   l.get("energie_klasse", ""),
                "balkon":           l.get("balkon", False),
                "keller":           l.get("keller", False),
                "aufzug":           l.get("aufzug", False),
                "kaltmiete":        l.get("kaltmiete_geschaetzt"),
                "roi":              l.get("roi"),
                "brutto_rendite":   l.get("brutto_rendite"),
                "cashflow_mo":      l.get("cashflow_mo"),
                "monatsrate":       l.get("monatsrate"),
                "darlehen":         l.get("darlehen"),
                "bewertung":        l.get("bewertung", ""),
                "marktwert_diff_pct": l.get("marktwert_diff_pct"),
                "url":              l.get("url", ""),
                "bilder":           l.get("bilder", []),
                "quelle":           l.get("quelle", "immoscout24"),
                "scraped_at":       datetime.utcnow().isoformat(),
            })

        try:
            result = (
                self._client.table("listings")
                .upsert(rows, on_conflict="id")
                .execute()
            )
            count = len(result.data) if result.data else 0
            logger.info(f"✓ Saved {count} listings to Supabase")
            return count
        except Exception as e:
            logger.error(f"Supabase save error: {e}")
            return 0

    async def get_listings(
        self,
        ort: Optional[str] = None,
        min_roi: Optional[float] = None,
        limit: int = 50
    ) -> list:
        """Query saved listings from Supabase."""
        if not self._client:
            return []
        try:
            query = self._client.table("listings").select("*").limit(limit)
            if ort:
                query = query.ilike("ort", f"%{ort}%")
            if min_roi:
                query = query.gte("roi", min_roi)
            query = query.order("roi", desc=True)
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Supabase query error: {e}")
            return []
